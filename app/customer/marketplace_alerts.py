"""Marketplace ke scheduled alerts (cron / `python manage.py marketplace_alerts`).

1. Vendor ne order accept nahi kiya: 5 min -> store manager, 10 min -> admin (escalation).
2. Order late (tayyari / raste mein) aur "rider chahiye" -> admin (rider chahiye par vendor ko bhi).
3. Vendor / rider document expiry: 30 din, 7 din, expiry wale din, aur expire ho jane par.
4. Rider shift reminder (shift se 30 min pehle) aur rider cash limit.

Har alert ek hi baar jata hai (group_key + Notification table se pata chalta hai), isliye command har minute
chalane se spam nahi hota. Faisle ke rules Django-free: app/utils/marketplace_alert_rules.py.
"""
import logging
from datetime import datetime, timedelta

from django.utils import timezone

from ..utils import marketplace_alert_rules as ar
from ..utils import marketplace_ops_rules as ops
from . import store_orders

logger = logging.getLogger(__name__)

ACTIVE = ('pending', 'confirmed', 'processing', 'ready')


# ---------------------------------------------------------------- helpers
def _notif_model():
    from ..models import Notification
    return Notification


def _gk(event, ctx):
    from ..utils.notification_rules import render_event
    return render_event(event, ctx)['group_key']


def _sent(event, group_key, user=None, within_hours=None):
    """Ye alert pehle ja chuka hai? (user=None: kisi bhi user ko gaya ho)"""
    qs = _notif_model().objects.filter(event=event, group_key=group_key)
    if user is not None:
        qs = qs.filter(user=user)
    if within_hours:
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(hours=within_hours))
    return qs.exists()


def _vendor_targets(profile, managers_only=False):
    """Store ke users. managers_only: sirf manager role; koi nahi to owner."""
    from ..models import VendorStaff
    from django.db.models import Q
    root = profile.parent if profile.parent_id else profile
    if managers_only:
        staff = (VendorStaff.objects.filter(is_active=True, role=VendorStaff.ROLE_MANAGER)
                 .filter(Q(store=profile) | Q(extra_stores=profile)).select_related('user').distinct())
        users = [r.user for r in staff if r.user and r.user.is_active]
        return users or [root.user]
    from .vendor_access import notify_users
    return notify_users(profile)


# ---------------------------------------------------------------- 1 + 2: live orders
def check_live_orders(now=None):
    """Escalation + late + rider needed. Wapas dict counts."""
    from ..models import SaleOrder
    from ..utils.admin_alerts import notify_admins
    now = now or timezone.now()
    out = {'manager': 0, 'admin': 0, 'late': 0, 'rider_needed': 0}
    expire_min = store_orders.accept_timeout_minutes()
    qs = (SaleOrder.objects.filter(vendor__isnull=False, status__in=ACTIVE)
          .select_related('vendor', 'delivery_info').order_by('created_at'))
    for o in qs[:500]:
        try:
            store = store_orders.store_name(o.vendor_id)
            d = getattr(o, 'delivery_info', None)      # DeliveryInfo na ho to None
            start = o.created_at
            if o.scheduled_for:          # schedule wala order: clock schedule se 1 ghanta pehle shuru
                start = max(start, o.scheduled_for - timedelta(minutes=store_orders.SCHEDULE_LEAD_MINUTES))
                if start > now:
                    continue
            age = ops.minutes_between(start, now)
            stage = ops.order_stage(o.status, d.status if d else None)
            if stage is None:
                continue
            ctx = {'order_no': o.order_no, 'store': store, 'store_id': o.vendor_id}

            if stage == ops.STAGE_NEW:
                level = ar.escalation_stage(age, expire_min)
                if level is None:
                    continue
                prof = store_orders.get_store_profile(o.vendor_id)
                mins = int(age)
                c = dict(ctx, minutes=mins)
                if prof and not _sent('order_unanswered_manager', _gk('order_unanswered_manager', c)):
                    for u in _vendor_targets(prof, managers_only=True):
                        store_orders._notify_event(u, 'order_unanswered_manager', c, '/shop/vendor/orders/',
                                                   push_kind='vendor')
                    out['manager'] += 1
                if level == 'admin' and not _sent('order_unanswered_admin', _gk('order_unanswered_admin', c)):
                    notify_admins('order_unanswered_admin', c, link=f'/orders/sale/{o.pk}/')
                    out['admin'] += 1
                continue

            has_rider = bool(d and d.rider_id)
            since_ready = ops.minutes_between(o.updated_at, now) if stage == ops.STAGE_READY else None
            since_pickup = ops.minutes_between(d.picked_up_at, now) if (d and d.picked_up_at) else None
            late = ops.order_late_reason(stage, age, o.prep_minutes, has_rider, since_ready, since_pickup)
            if not late:
                continue
            if stage == ops.STAGE_READY:         # ready + rider nahi
                if not _sent('rider_needed', _gk('rider_needed', ctx)):
                    notify_admins('rider_needed', ctx, link='/marketplace/dispatch/')
                    prof = store_orders.get_store_profile(o.vendor_id)
                    if prof:
                        for u in _vendor_targets(prof):
                            store_orders._notify_event(u, 'rider_needed', ctx, '/shop/vendor/orders/?tab=active')
                    out['rider_needed'] += 1
            elif not _sent('order_late', _gk('order_late', ctx)):
                notify_admins('order_late', dict(ctx, reason=late), link=f'/orders/sale/{o.pk}/')
                out['late'] += 1
        except Exception:
            logger.exception('live order alert failed (order %s)', getattr(o, 'pk', '?'))
    return out


# ---------------------------------------------------------------- 3: document expiry
def _expiry_ctx(doc_label, expiry, today, **extra):
    m = ar.expiry_milestone(expiry, today)
    if m is None:
        return None, None
    ctx = dict(extra, document=doc_label, date=expiry.strftime('%d %b %Y'), date_key=ar.date_key(expiry))
    if m != 'expired':
        ctx.update(milestone=m, when=ar.expiry_when(m))
    return m, ctx


def check_vendor_documents(today=None):
    from ..models import VendorDocument
    from ..utils.admin_alerts import notify_admins
    from .vendor_docs import KIND_LABELS
    today = today or timezone.localdate()
    sent = 0
    docs = (VendorDocument.objects.filter(status='approved', expiry__isnull=False)
            .select_related('store', 'store__user'))
    for doc in docs:
        try:
            label = KIND_LABELS.get(doc.kind, doc.kind)
            m, ctx = _expiry_ctx(label, doc.expiry, today, store_id=doc.store_id, kind=doc.kind,
                                 business=doc.store.business_name)
            if m is None:
                continue
            ev = 'vendor_doc_expired' if m == 'expired' else 'vendor_doc_expiring'
            gk = _gk(ev, ctx)
            if _sent(ev, gk):
                continue
            for u in _vendor_targets(doc.store, managers_only=True):
                store_orders._notify_event(u, ev, ctx, '/shop/vendor/documents/')
            notify_admins('admin_vendor_doc_expired' if m == 'expired' else 'admin_vendor_doc_expiring', ctx,
                          link=f'/vendors/{doc.store_id}/documents/')
            sent += 1
        except Exception:
            logger.exception('vendor doc alert failed (doc %s)', doc.pk)
    return sent


def check_rider_documents(today=None):
    from ..models import RiderDocument
    from .rider_docs import KIND_LABELS
    today = today or timezone.localdate()
    sent = 0
    docs = (RiderDocument.objects.filter(status='approved', expiry__isnull=False, rider__is_active=True)
            .select_related('rider', 'rider__user'))
    for doc in docs:
        try:
            if not doc.rider.user_id:
                continue
            label = KIND_LABELS.get(doc.kind, doc.kind)
            m, ctx = _expiry_ctx(label, doc.expiry, today, rider_id=doc.rider_id, kind=doc.kind)
            if m is None:
                continue
            ev = 'rider_doc_expired' if m == 'expired' else 'rider_doc_expiring'
            if _sent(ev, _gk(ev, ctx), user=doc.rider.user):
                continue
            store_orders._notify_event(doc.rider.user, ev, ctx, '/shop/rider/documents/')
            sent += 1
        except Exception:
            logger.exception('rider doc alert failed (doc %s)', doc.pk)
    return sent


# ---------------------------------------------------------------- 4: shifts + cash
def check_shift_reminders(now=None):
    from ..models import RiderShiftBooking
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    sent = 0
    bookings = (RiderShiftBooking.objects.filter(status='booked', shift__date__in=[today, today + timedelta(days=1)])
                .select_related('shift', 'rider', 'rider__user'))
    for b in bookings:
        try:
            sh = b.shift
            start = timezone.make_aware(datetime.combine(sh.date, sh.start_time))
            mins = (start - now).total_seconds() / 60
            if not ar.shift_reminder_due(mins) or not b.rider.user_id:
                continue
            ctx = {'minutes': int(mins), 'start': f'{sh.start_time:%H:%M}', 'end': f'{sh.end_time:%H:%M}',
                   'zone': f' ({sh.zone})' if sh.zone else '', 'shift_id': sh.pk}
            if _sent('rider_shift_reminder', _gk('rider_shift_reminder', ctx), user=b.rider.user):
                continue
            store_orders._notify_event(b.rider.user, 'rider_shift_reminder', ctx, '/shop/rider/shifts/',
                                       push_kind='rider')
            sent += 1
        except Exception:
            logger.exception('shift reminder failed (booking %s)', b.pk)
    return sent


def check_rider_cash():
    from ..models import RiderProfile
    from ..utils.admin_alerts import notify_admins
    from . import goals
    from .views_rider_portal import rider_balances, _setting_num
    limit = _setting_num('rider_cash_limit')
    if not limit or limit <= 0:
        return 0
    sent = 0
    for rider in RiderProfile.objects.filter(is_active=True, approval_status='approved').select_related('user'):
        try:
            st = goals.cash_state(rider_balances(rider)['cash_in_hand'], limit)
            if not st or st['level'] == 'ok':
                continue
            ev = 'rider_cash_over' if st['level'] == 'over' else 'rider_cash_warn'
            ctx = {'rider_id': rider.pk, 'rider': rider.name, 'cash': f"Rs. {st['cash']:,.0f}",
                   'limit': f"Rs. {st['limit']:,.0f}"}
            gk = _gk(ev, ctx)
            if rider.user_id and not _sent(ev, gk, user=rider.user, within_hours=ar.CASH_REPEAT_HOURS):
                store_orders._notify_event(rider.user, ev, ctx, '/shop/rider/earnings/')
                sent += 1
            if st['level'] == 'over' and not _sent('admin_rider_cash_over', _gk('admin_rider_cash_over', ctx),
                                                   within_hours=ar.CASH_REPEAT_HOURS):
                notify_admins('admin_rider_cash_over', ctx, link='/marketplace/dispatch/')
        except Exception:
            logger.exception('rider cash alert failed (rider %s)', rider.pk)
    return sent


def run_all():
    res = {}
    for name, fn in (('orders', check_live_orders), ('vendor_docs', check_vendor_documents),
                     ('rider_docs', check_rider_documents), ('shifts', check_shift_reminders),
                     ('cash', check_rider_cash)):
        try:
            res[name] = fn()
        except Exception:
            logger.exception('marketplace alert step failed: %s', name)
            res[name] = 'error'
    return res
