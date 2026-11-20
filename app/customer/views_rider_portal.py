"""
Rider system (Talabat jaisa).

Rider:  login -> Online -> "Naye orders" (offers) mein se Accept (jo pehle accept kare uska) ->
        Maal le liya -> Deliver ho gaya (COD cash + kamai darj) ; History, Earnings.
Vendor: Ready karne ke baad khud rider chun sakta hai ya offers se koi rider le leta hai.
Admin:  riders banata/band karta hai, fee set karta hai, rider ka cash jama / kamai ki ada'egi darj karta hai.
"""
import logging
from functools import wraps

from django.conf import settings
from .vendor_access import get_vendor_profile
from django.contrib import messages
from django.contrib.auth import authenticate, logout
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from ..shop_flags import flag_required, shop_flag
from django.utils import timezone
from urllib.parse import quote
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.http import require_POST

from ..decorators import vendor_login_required
from ..models import (
    CompanyInfo, DeliveryInfo, OrderTracking, RiderBonus, RiderProfile, RiderSettlement, SaleOrder, VendorProfile,
)
from . import store_orders
from ..i18n.server_t import tr
from ..utils.password_policy import first_error
from . import dispatch
from . import batching
from . import demand
from . import goals
from . import rider_gate
from . import rider_nav
from . import rider_peak
from .views_reviews import rider_rating
from .views_customer_auth import get_client_ip, is_valid_phone, normalize_phone, safe_login

logger = logging.getLogger(__name__)

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 10 * 60

ACTIVE_STATUSES = ['assigned', 'picked_up', 'in_transit']
MAX_ACTIVE_ORDERS = 3          # ek rider ek waqt mein itne orders tak


# ============================================
# HELPERS
# ============================================

def _company_name():
    company = CompanyInfo.objects.first()
    return company.name if company else 'Shop'


def rider_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, '🔒 Please log in as a rider first')
            return redirect('rider_login')
        profile = getattr(request.user, 'rider_profile', None)
        if profile is None:
            messages.error(request, '❌ This page is for riders only')
            return redirect('shop_home')
        if not profile.is_active:
            logout(request)
            messages.error(request, '❌ Your rider account is disabled. Please contact the admin.')
            return redirect('rider_login')
        return view_func(request, *args, **kwargs)
    return wrapper


def _track(order, status, title, description, user, rider=None):
    OrderTracking.objects.create(
        sale_order=order, status=status, title=title, description=description,
        rider_name=getattr(rider, 'name', None), rider_contact=getattr(rider, 'phone', None),
        updated_by=user,
    )


def _vendor_user(order):
    if not order.vendor_id:
        return None
    vp = VendorProfile.objects.filter(vendor_id=order.vendor_id).select_related('user').first()
    return vp.user if vp else None



# ============================================
# CALCULATIONS
# ============================================

def _D(v):
    return Decimal(v or 0)


def rider_balances(rider):
    """Cash jo rider ke paas hai aur kamai jo usay milni hai."""
    d = DeliveryInfo.objects.filter(rider=rider, status='delivered').aggregate(
        cash=Sum('cash_collected'), earned=Sum('rider_fee'), peak=Sum('peak_bonus'), n=Count('id'))
    st = {r['kind']: _D(r['t']) for r in rider.settlements.values('kind').annotate(t=Sum('amount'))}
    cash, fees = _D(d['cash']), _D(d['earned'])
    bonus = _D(rider.bonuses.aggregate(t=Sum('amount'))['t'])
    tips = _D(rider.tips.aggregate(t=Sum('amount'))['t'])
    ffees = _D(rider.delivery_failures.filter(status__in=('returned', 'closed'), returned_at__isnull=False)
               .aggregate(t=Sum('rider_fee'))['t'])
    fees += ffees
    earned = fees + bonus + tips
    return {
        'bonus': bonus, 'fees': fees, 'tips': tips, 'peak': _D(d['peak']),
        'deliveries': d['n'] or 0,
        'cash_collected': cash,
        'cash_deposited': st.get('cash_in', Decimal('0')),
        'cash_in_hand': cash - st.get('cash_in', Decimal('0')),
        'earned': earned,
        'paid_out': st.get('payout', Decimal('0')),
        'due': earned - st.get('payout', Decimal('0')),
    }


def period_stats(rider, since_date):
    a = DeliveryInfo.objects.filter(rider=rider, status='delivered', delivered_at__date__gte=since_date)\
        .aggregate(n=Count('id'), earned=Sum('rider_fee'))
    tips = _D(rider.tips.filter(created_at__date__gte=since_date).aggregate(t=Sum('amount'))['t'])
    ff = _D(rider.delivery_failures.filter(returned_at__date__gte=since_date).aggregate(t=Sum('rider_fee'))['t'])
    return {'deliveries': a['n'] or 0, 'earned': _D(a['earned']) + tips + ff}


def _setting_num(name):
    from .offers import setting_decimal
    return setting_decimal(name, '0')


def _goal_cfg():
    return {
        'daily': (int(_setting_num('rider_goal_daily_orders')), _setting_num('rider_goal_daily_bonus')),
        'weekly': (int(_setting_num('rider_goal_weekly_orders')), _setting_num('rider_goal_weekly_bonus')),
    }


def _goal_periods():
    today = timezone.localdate()
    return {'daily': today, 'weekly': goals.week_start(today)}


def _goals_ctx(rider):
    """Rider ke goals ki progress: [{'kind','label','done','goal','bonus','pct','left','reached','paid'}]."""
    out = []
    periods = _goal_periods()
    cfg = _goal_cfg()
    labels = {'daily': "Today's goal", 'weekly': "This week's goal"}
    for kind in ('daily', 'weekly'):
        goal, bonus = cfg[kind]
        p = goals.progress(period_stats(rider, periods[kind])['deliveries'], goal, bonus)
        if not p:
            continue
        p.update(kind=kind, label=labels[kind],
                 paid=rider.bonuses.filter(kind=kind, period_start=periods[kind]).exists())
        out.append(p)
    return out


def _award_goal_bonuses(rider):
    """Delivery ke baad: jo goal poora hua aur bonus abhi nahi mila, woh de do. Naye bonuses ki list lautata hai."""
    given = []
    periods = _goal_periods()
    for kind, (goal, bonus) in _goal_cfg().items():
        if goal <= 0 or bonus <= 0:
            continue
        n = period_stats(rider, periods[kind])['deliveries']
        if n < goal:
            continue
        _obj, created = RiderBonus.objects.get_or_create(
            rider=rider, kind=kind, period_start=periods[kind],
            defaults={'amount': bonus, 'deliveries': n})
        if created:
            given.append((kind, bonus))
    return given


def _cash_ctx(rider, balances=None):
    b = balances or rider_balances(rider)
    return goals.cash_state(b['cash_in_hand'], _setting_num('rider_cash_limit'))


def _touch(rider):
    RiderProfile.objects.filter(pk=rider.pk).update(last_seen_at=now())


def _maps(addr):
    return 'https://www.google.com/maps/search/?api=1&query=' + quote(addr) if addr else ''


def _nav_links(lat, lng, addr):
    """Google Maps / Waze ke turn-by-turn navigation links. Coordinates ko tarjih, warna address."""
    if lat is not None and lng is not None:
        dest = f'{lat},{lng}'
        return {
            'google': f'https://www.google.com/maps/dir/?api=1&destination={dest}&travelmode=two-wheeler&dir_action=navigate',
            'waze': f'https://waze.com/ul?ll={dest}&navigate=yes',
        }
    if addr:
        q = quote(addr)
        return {
            'google': f'https://www.google.com/maps/dir/?api=1&destination={q}&travelmode=two-wheeler&dir_action=navigate',
            'waze': f'https://waze.com/ul?q={q}&navigate=yes',
        }
    return None


def _nav_for_leg(di, o, store_addr, cust_addr):
    """Rider ab kahan ja raha hai: 'assigned' = store, uske baad = customer."""
    if di.status == 'assigned':
        s_lat, s_lng = dispatch._store_coords(o)
        links = _nav_links(s_lat, s_lng, store_addr)
        return ('store', links) if links else (None, None)
    links = _nav_links(o.delivery_lat, o.delivery_lng, cust_addr)
    return ('customer', links) if links else (None, None)


def _card(di):
    o = di.sale_order
    cust = o.customer
    store_addr = getattr(o.vendor, 'address', '') if o.vendor_id else ''
    phone = (getattr(cust, 'contact_number', '') or '')
    digits = ''.join(ch for ch in phone if ch.isdigit())
    cust_addr = o.ship_address()
    nav_leg, nav = _nav_for_leg(di, o, store_addr, cust_addr)
    from . import delivery_returns, store_issues
    fail = delivery_returns.open_failure(di) if di.status in ('picked_up', 'in_transit') else None
    fail_left = delivery_returns.seconds_left(fail) if fail else 0
    return {
        'fail': fail, 'fail_min': -(-fail_left // 60), 'fail_left': fail_left,
        'fail_reasons': delivery_returns.REASONS,
        'store_issue': store_issues.open_issue(di) if di.status == 'assigned' else None,
        'issue_reasons': store_issues.reasons(),
        'nav_leg': nav_leg, 'nav': nav,
        'nav_inapp': rider_nav.leg_dest(di)['lat'] is not None,
        'di': di, 'order': o, 'items': list(o.items.all()),
        'store': store_orders.store_name(o.vendor_id),
        'store_phone': getattr(o.vendor, 'contact_number', '') if o.vendor_id else '',
        'store_addr': store_addr, 'map_store': _maps(store_addr),
        'cust_addr': cust_addr, 'map_cust': _maps(cust_addr),
        'map_pin': (f'https://www.google.com/maps/dir/?api=1&destination={o.delivery_lat},{o.delivery_lng}'
                    if o.delivery_lat is not None and o.delivery_lng is not None else ''),
        'cust_phone': phone, 'wa_cust': f'https://wa.me/{digits}' if digits else '',
        'total': store_orders.order_cash_due(o),
        'is_cod': (o.payment_method or 'cod') == 'cod',
    }


def _bv_job_card(o):
    """Bari gari wale driver ke liye ek job ka card (store se uthao, customer ko do)."""
    cust = o.customer
    store_addr = getattr(o.vendor, 'address', '') if o.vendor_id else ''
    cust_addr = o.ship_address()
    approved = o.big_vehicle_state == 'approved'
    phone = (getattr(cust, 'contact_number', '') or '') if approved else ''      # number tab dikhta hai jab kiraya manzoor ho
    digits = ''.join(ch for ch in phone if ch.isdigit())
    return {
        'order': o, 'approved': approved, 'fee': o.big_vehicle_fee,
        'pending': o.big_vehicle_driver_state == 'pending', 'accepted': o.big_vehicle_driver_state == 'accepted',
        'store': store_orders.store_name(o.vendor_id), 'store_addr': store_addr, 'map_store': _maps(store_addr),
        'store_phone': getattr(o.vendor, 'contact_number', '') if o.vendor_id else '',
        'cust_addr': cust_addr, 'map_cust': _maps(cust_addr),
        'cust_name': getattr(cust, 'name', '') if approved else '', 'cust_phone': phone,
        'wa_cust': f'https://wa.me/{digits}' if digits else '',
        'items_count': o.items.count(),
        'total': store_orders.order_cash_due(o) if approved else None,
        # Driver sirf apna kiraya leta hai; baqi raqam (items) store ki hai
        'items_due': max((store_orders.order_cash_due(o) or Decimal('0')) - (o.big_vehicle_fee or Decimal('0')), Decimal('0')) if approved else None,
        'is_cod': (o.payment_method or 'cod') == 'cod',
        'ready': o.status == 'ready',
    }


def _bv_jobs(rider):
    """Is gari ke maujooda jobs: customer ki manzoori ka intezar (proposed) ya manzoor (approved), jab tak deliver na ho."""
    if rider.rider_kind != 'big_vehicle':
        return []
    qs = (SaleOrder.objects.filter(big_vehicle_driver=rider, big_vehicle_state__in=('proposed', 'approved'),
                                   status__in=('confirmed', 'processing', 'ready'))
          .select_related('customer', 'vendor').prefetch_related('items').order_by('-big_vehicle_proposed_at'))
    return [_bv_job_card(o) for o in qs[:30]]


def _offers_qs():
    """Ready orders jinka abhi koi rider nahi."""
    taken = DeliveryInfo.objects.filter(rider__isnull=False, sale_order__isnull=False).values('sale_order_id')
    return (SaleOrder.objects.filter(status='ready', vendor__isnull=False)
            .exclude(big_vehicle_state__in=['proposed', 'approved'])   # bari gari: store khud deliver karta hai
            .exclude(pk__in=taken).select_related('customer', 'vendor')
            .prefetch_related('items__product').order_by('vendor_responded_at')[:20])


def _ll(lat, lng):
    return (float(lat), float(lng)) if lat is not None and lng is not None else None


def _batch_info(o):
    """Order ki batching ke liye zaroori maloomat."""
    s_lat, s_lng = dispatch._store_coords(o)
    cust = o.customer
    return {
        'order_no': o.order_no, 'order_id': o.id, 'vendor_id': o.vendor_id,
        'store_name': store_orders.store_name(o.vendor_id),
        'store_ll': _ll(s_lat, s_lng),
        'store_addr': getattr(o.vendor, 'address', '') if o.vendor_id else '',
        'cust_name': getattr(cust, 'name', '') or '',
        'drop_ll': _ll(o.delivery_lat, o.delivery_lng),
        'cust_addr': o.ship_address(),
    }


BATCH_LABELS = {
    'same_store': '🔗 Same store as your order — pick up together',
    'near_store': '🔗 Near your order\'s store — pick up together',
    'same_area': '🔗 In your customer\'s area — on the same route',
}


def _offer_card(o, rider, actives=None):
    cust = o.customer
    _peak = rider_peak.bonus_now()
    store_addr = getattr(o.vendor, 'address', '') if o.vendor_id else ''
    return {
        'order': o, 'items_count': sum(1 for _ in o.items.all()),
        'store': store_orders.store_name(o.vendor_id), 'store_addr': store_addr,
        'cust_addr': o.ship_address(),
        'total': store_orders.order_cash_due(o),
        'is_cod': (o.payment_method or 'cod') == 'cod',
        'fee': Decimal(rider.per_delivery_fee or 0) + _peak,
        'peak': _peak,
        'dist_km': dispatch.distance_km(o, rider),
        'batch': BATCH_LABELS.get(batching.match_offer(_batch_info(o), actives or [])),
    }


def _assign(order, di, rider, user):
    """Rider ko order do (vendor ke chunne par ya rider ke accept karne par)."""
    di.delivery_type = 'local_rider'
    di.rider = rider
    di.rider_name = rider.name
    di.rider_contact = rider.phone
    di.rider_vehicle = rider.vehicle
    di.status = 'assigned'
    di.assigned_at = now()
    di.peak_bonus = rider_peak.bonus_now()
    di.created_by = user
    di.save()
    _track(order, 'rider_assigned', 'Rider Assigned', f'Rider: {rider.name} ({rider.phone})', user, rider)
    store_orders._notify_event(store_orders._customer_user(order), 'rider_assigned_customer',
                               {'order_no': order.order_no, 'rider': rider.name, 'phone': rider.phone},
                               f'/shop/order/{order.id}/')
    store_orders._notify(_vendor_user(order), f'🏍️ Order #{order.order_no}: rider {rider.name} is coming',
                         f'{rider.name} ({rider.phone}) is on the way to pick up the order.',
                         '/shop/vendor/orders/?tab=active', 'info', category='riders')


# ============================================
# RIDER LOGIN / LOGOUT
# ============================================

@flag_required('rider_login_enabled', redirect_to='shop_home')
def rider_login(request):
    if request.user.is_authenticated and hasattr(request.user, 'rider_profile'):
        return redirect('rider_home')

    if request.method == 'POST':
        phone_raw = request.POST.get('phone', '').strip()[:20]
        password = request.POST.get('password', '')
        if not phone_raw or not password:
            messages.error(request, '❌ Enter both phone and password')
            return redirect('rider_login')

        phone = normalize_phone(phone_raw)
        key = f"rider_login:{phone}:{get_client_ip(request) or ''}"
        if cache.get(key, 0) >= LOGIN_MAX_ATTEMPTS:
            messages.error(request, '🔒 Too many attempts. Please try again after 10 minutes.')
            return redirect('rider_login')

        rider = RiderProfile.objects.select_related('user').filter(phone=phone, is_active=True).first()
        user = authenticate(request, username=rider.user.username, password=password) if rider else None
        if not rider:
            waiting = RiderProfile.objects.select_related('user').filter(phone=phone, is_active=False).first()
            if waiting and authenticate(request, username=waiting.user.username, password=password):
                messages.info(request, '⏳ Your registration is waiting for admin approval.')
                return redirect('rider_login')
        if not user:
            cache.set(key, cache.get(key, 0) + 1, LOGIN_LOCK_SECONDS)
            messages.error(request, '❌ Phone or password is incorrect')
            return redirect('rider_login')

        cache.delete(key)
        safe_login(request, user)
        request.session.save()
        rider.last_login_at = now()
        rider.save(update_fields=['last_login_at'])
        return redirect('rider_home')

    return render(request, 'customer_portal/rider/login.html', {'company_name': _company_name()})


@flag_required('rider_register_enabled', redirect_to='shop_home')
def rider_register(request):
    """Rider khud register kare. Admin approval ke baghair login nahi (jab tak 'Auto-approve new riders' OFF ho)."""
    if request.user.is_authenticated and hasattr(request.user, 'rider_profile'):
        return redirect('rider_home')

    form = {}
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()[:100]
        phone_raw = request.POST.get('phone', '').strip()[:20]
        vehicle = request.POST.get('vehicle', '').strip()[:50]
        password = request.POST.get('password', '')
        confirm = request.POST.get('confirm', '')
        form = {'name': name, 'phone': phone_raw, 'vehicle': vehicle}
        key = 'rider_register:%s' % (get_client_ip(request) or '')

        error = None
        if cache.get(key, 0) >= 5:
            error = '🔒 Too many registrations. Please try again later.'
        elif not name or not phone_raw:
            error = '❌ Enter your name and phone number.'
        elif not is_valid_phone(phone_raw):
            error = '❌ Phone number is not valid.'
        elif first_error(password, (name, phone_raw)):
            error = '❌ ' + first_error(password, (name, phone_raw))
        elif password != confirm:
            error = '❌ Both passwords must be the same.'

        if not error:
            phone = normalize_phone(phone_raw)
            username = 'rider_' + phone.replace('+', '')
            docs_flow = shop_flag('rider_documents_required')     # documents upload + approval (Talabat jaisa)
            auto = True if docs_flow else shop_flag('rider_auto_approve')
            try:
                with transaction.atomic():
                    user = User.objects.create_user(username=username, password=password, first_name=name[:30])
                    RiderProfile.objects.create(user=user, name=name, phone=phone, vehicle=vehicle, is_active=auto,
                                                approval_status='pending' if docs_flow else 'approved')
            except IntegrityError:
                error = '❌ A rider with this phone already exists.'
            else:
                cache.set(key, cache.get(key, 0) + 1, 3600)
                if docs_flow:
                    messages.success(request, '✅ Registration complete. Log in and upload your documents (CPR, licence, vehicle, photo) for approval.')
                elif auto:
                    messages.success(request, '✅ Registration complete. You can log in now.')
                else:
                    messages.success(request, '✅ Registration received. You can log in after admin approval.')
                return redirect('rider_login')
        messages.error(request, error)

    return render(request, 'customer_portal/rider/register.html', {'company_name': _company_name(), 'form': form})


def rider_logout(request):
    rp = getattr(request.user, 'rider_profile', None) if request.user.is_authenticated else None
    if rp:
        RiderProfile.objects.filter(pk=rp.pk).update(is_online=False)
    request.session.flush()
    logout(request)
    messages.success(request, '👋 You have been logged out.')
    return redirect('rider_login')


# ============================================
# RIDER SCREENS
# ============================================

def _dispute_pending(rider):
    from .disputes import needs_response_count
    return needs_response_count('rider', rider)


def _rider_ctx(request, nav, **extra):
    rider = request.user.rider_profile
    active_n = DeliveryInfo.objects.filter(rider=rider, status__in=ACTIVE_STATUSES).count()
    offer_n = 0
    try:   # naye offers bhi Orders tab ke badge mein (rider_poll jaisi hi shart)
        if rider.is_online and rider_gate.work_status(rider)[0]:
            offer_n = len(dispatch.visible_orders(_offers_qs(), rider, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES))
    except Exception:
        offer_n = 0
    bv_n = rider.big_vehicle_jobs.filter(big_vehicle_state='approved',
                                         status__in=('confirmed', 'processing', 'ready')).count() if rider.rider_kind == 'big_vehicle' else 0
    ctx = {'rider': rider, 'nav': nav, 'company_name': _company_name(),
           'active_count': active_n + bv_n, 'badge_count': active_n + offer_n + bv_n,
           'dispute_count': _dispute_pending(rider)}
    try:
        from .rider_support import unread_for_rider
        ctx['support_unread'] = unread_for_rider(rider)
    except Exception:
        ctx['support_unread'] = 0
    try:   # "More" tab ka badge: issues + documents ki warning (har page par)
        ctx['doc_warn_n'] = len(rider_gate.doc_warnings(rider))
    except Exception:
        ctx['doc_warn_n'] = 0
    ctx['more_badge'] = (ctx['dispute_count'] or 0) + ctx['doc_warn_n']
    ctx['unassign_reasons'] = UNASSIGN_REASONS
    try:
        ctx['peak_now'] = rider_peak.current()
    except Exception:
        ctx['peak_now'] = None
    ctx.update(extra)
    return ctx


@rider_login_required
def rider_home(request):
    rider = request.user.rider_profile
    _touch(rider)
    mine = (DeliveryInfo.objects.filter(rider=rider, status__in=ACTIVE_STATUSES, sale_order__isnull=False)
            .select_related('sale_order', 'sale_order__customer', 'sale_order__vendor')
            .prefetch_related('sale_order__items__product').order_by('assigned_at'))
    actives = [_batch_info(d.sale_order) for d in mine]
    can_work, gate_msg = rider_gate.work_status(rider)
    offers = [_offer_card(o, rider, actives) for o in dispatch.visible_orders(_offers_qs(), rider, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES)] if (rider.is_online and can_work) else []
    # ek raaste ke offers pehle
    offers.sort(key=lambda c: 0 if c['batch'] else 1)
    plan = batching.plan_route(
        [dict(a, status=d.status) for a, d in zip(actives, mine)],
        dispatch._rider_coords(rider, now()) if actives else None)
    today = period_stats(rider, timezone.localdate())
    bal = rider_balances(rider)
    return render(request, 'customer_portal/rider/home.html', _rider_ctx(
        request, 'orders', mine=[_card(d) for d in mine], offers=offers, plan=plan,
        today=today, balances=bal, max_active=MAX_ACTIVE_ORDERS,
        goal_list=_goals_ctx(rider), cash=_cash_ctx(rider, bal),
        gate_msg=gate_msg, doc_warnings=rider_gate.doc_warnings(rider), next_shift=rider_gate.next_shift(rider),
        bv_jobs=_bv_jobs(rider), is_big_vehicle=(rider.rider_kind == 'big_vehicle')))


DEMAND_CACHE_SECONDS = 300


def _demand_rows():
    """Pichle 28 din ke delivery orders: [(weekday, hour, vendor_id)]. 5 minute cache (sab riders ke liye ek)."""
    key = 'rider_demand_rows_v1'
    rows = cache.get(key)
    if rows is not None:
        return rows
    since = now() - timedelta(days=demand.WINDOW_DAYS)
    qs = (SaleOrder.objects.filter(created_at__gte=since, delivery_info__isnull=False)
          .exclude(status='cancelled').values_list('created_at', 'vendor_id')[:20000])
    rows = []
    for dt, vid in qs:
        loc = timezone.localtime(dt)
        rows.append((loc.weekday(), loc.hour, vid))
    cache.set(key, rows, DEMAND_CACHE_SECONDS)
    return rows


@rider_login_required
@flag_required('rider_hotspots_enabled', redirect_to='rider_home')
def rider_hotspots(request):
    """Heat map (kahan orders zyada hain) + shift planner (kab kaam karna behtar hai)."""
    rider = request.user.rider_profile
    _touch(rider)
    rows = _demand_rows()
    vids = {v for _w, _h, v in rows if v}
    stores = {}
    for p in VendorProfile.objects.filter(vendor_id__in=vids).values('vendor_id', 'business_name', 'lat', 'lng'):
        stores[p['vendor_id']] = {'name': p['business_name'], 'lat': _f(p['lat']), 'lng': _f(p['lng'])}

    local = timezone.localtime()
    wd, hr = local.weekday(), local.hour
    near_hours = {hr, (hr + 1) % 24, (hr + 2) % 24}
    today_profile = demand.hour_profile(rows, wd)
    data = {
        'zones_now': demand.zones(rows, stores, hours=near_hours, weekday=wd),
        'zones_day': demand.zones(rows, stores, weekday=wd),
        'zones_all': demand.zones(rows, stores),
        'profile': today_profile, 'hour': hr,
        'my': ([float(rider.last_lat), float(rider.last_lng)]
               if rider.last_lat is not None and rider.last_lng is not None else None),
    }
    return render(request, 'customer_portal/rider/hotspots.html', _rider_ctx(
        request, 'hotspots', data=data, today_name=demand.DAY_NAMES[wd],
        plan=demand.weekly_plan(rows), today_window=demand.best_window(today_profile),
        has_data=bool(rows), has_zones=bool(data['zones_all']), max_hour=max(today_profile) or 1))


def _f(v):
    return float(v) if v is not None else None


@rider_login_required
def rider_history(request):
    rider = request.user.rider_profile
    qs = (DeliveryInfo.objects.filter(rider=rider, status__in=['delivered', 'returned', 'cancelled'], sale_order__isnull=False)
          .select_related('sale_order', 'sale_order__customer', 'sale_order__vendor')
          .order_by('-delivered_at', '-assigned_at')[:50])
    rows = [{'di': d, 'order': d.sale_order, 'store': store_orders.store_name(d.sale_order.vendor_id),
             'total': store_orders.order_cash_due(d.sale_order)} for d in qs]
    return render(request, 'customer_portal/rider/history.html', _rider_ctx(request, 'history', rows=rows))


def _payout_ctx(rider):
    from . import rider_payouts
    from ..models import RiderPayoutRequest
    reqs = list(rider.payout_requests.all()[:10])
    return {'on': shop_flag('rider_payout_request_enabled'), 's': rider_payouts.summary(rider),
            'pending': next((r for r in reqs if r.status == 'pending'), None),
            'methods': RiderPayoutRequest.METHODS, 'history': reqs}


@rider_login_required
@flag_required('rider_earnings_enabled', redirect_to='rider_home')
def rider_earnings(request):
    rider = request.user.rider_profile
    today = timezone.localdate()
    return render(request, 'customer_portal/rider/earnings.html', _rider_ctx(
        request, 'earnings',
        b=rider_balances(rider),
        today=period_stats(rider, today),
        week=period_stats(rider, today - timedelta(days=6)),
        rating=rider_rating(rider),
        goal_list=_goals_ctx(rider), cash=_cash_ctx(rider),
        bonuses=list(rider.bonuses.all()[:10]),
        tip_list=list(rider.tips.select_related('sale_order')[:10]),
        payout=_payout_ctx(rider),
        settlements=list(rider.settlements.all()[:20])))


@rider_login_required
def rider_settings(request):
    """Rider settings: profile, change password (alerts, battery saver and language live in the page itself)."""
    rider = request.user.rider_profile
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'profile':
            name = request.POST.get('name', '').strip()[:100]
            vehicle = request.POST.get('vehicle', '').strip()[:50]
            if len(name) < 2:
                messages.error(request, '❌ Enter your full name.')
            else:
                rider.name, rider.vehicle = name, vehicle
                rider.save(update_fields=['name', 'vehicle'])
                messages.success(request, '✅ Profile saved.')
        elif action == 'password':
            old = request.POST.get('old_password', '')
            new = request.POST.get('new_password', '')
            confirm = request.POST.get('confirm', '')
            if not request.user.check_password(old):
                messages.error(request, '❌ Your current password is not correct.')
            elif new != confirm:
                messages.error(request, '❌ The new passwords do not match.')
            elif first_error(new, (rider.name, rider.phone)):
                messages.error(request, '❌ ' + first_error(new, (rider.name, rider.phone)))
            else:
                from django.contrib.auth import update_session_auth_hash
                request.user.set_password(new)
                request.user.save()
                update_session_auth_hash(request, request.user)      # keep this rider logged in
                messages.success(request, '✅ Password changed.')
        return redirect('rider_settings')
    return render(request, 'customer_portal/rider/settings.html', _rider_ctx(request, 'settings'))


def _delayed_test_push(user_id, delay):
    """Settings > Test ring: thori der baad asli 'naya order' jaisi push (taake rider app band kar sake)."""
    import time
    from django.db import connection
    try:
        time.sleep(delay)
        from ..utils import push_service
        user = User.objects.filter(pk=user_id, is_active=True).first()
        if user:
            push_service.send_push(user, '\U0001F195 Test order', 'This is a ring test. Your phone is set up correctly.',
                                   reverse('rider_home'), 'rider', None)
    except Exception:
        logger.exception('rider test push failed')
    finally:
        try:
            connection.close()
        except Exception:
            pass


@rider_login_required
@require_POST
def rider_test_push(request):
    """Rider ke apne phone ki ring ka test + saaf wajah (kaunsi cheez ruki hui hai). Normal form POST -> flash message."""
    import threading
    from ..models import FcmDevice
    from ..utils import push_service
    delay = 15
    try:
        if not shop_flag('shop_push_enabled'):
            messages.error(request, '❌ Push notifications are turned OFF in the shop settings (shop_push_enabled).')
            return redirect('rider_settings')
    except Exception:
        pass
    if not push_service.fcm_is_configured():
        messages.error(request, '❌ Server Firebase key is missing or invalid (secret FIREBASE_SERVICE_ACCOUNT_BASE64).')
        return redirect('rider_settings')
    n = FcmDevice.objects.filter(user=request.user).count()
    if n == 0:
        messages.error(request, '❌ This phone is not registered for push. Install the NEW rider APK, open it, log in and tap Allow on the notification question.')
        return redirect('rider_settings')
    threading.Thread(target=_delayed_test_push, args=(request.user.pk, delay), daemon=True).start()
    messages.success(request, '✅ Test sent in %d seconds to %d phone(s). CLOSE the app now and wait.' % (delay, n))
    return redirect('rider_settings')


@rider_login_required
@require_POST
def rider_big_vehicle_respond(request, pk):
    from . import views_big_vehicle
    return views_big_vehicle.rider_big_vehicle_respond(request, pk)


@rider_login_required
@require_POST
def rider_big_vehicle_delivered(request, pk):
    from . import views_big_vehicle
    return views_big_vehicle.rider_big_vehicle_delivered(request, pk)


@rider_login_required
@require_POST
def rider_toggle_online(request):
    rider = request.user.rider_profile
    if not rider.is_online:                       # Online jaane se pehle approval / documents / shift check
        ok, why = rider_gate.work_status(rider)
        if not ok:
            messages.error(request, why)
            return redirect('rider_documents' if rider.approval_status != 'approved' else 'rider_home')
    rider.is_online = not rider.is_online
    rider.last_seen_at = now()
    rider.save(update_fields=['is_online', 'last_seen_at'])
    messages.success(request, '🟢 You are online. New order offers will appear.' if rider.is_online
                     else '⚫ You are offline. You will not get new offers.')
    return redirect('rider_home')


@rider_login_required
def rider_poll(request):
    """Har ~12 second mein: naye offers/orders ka count (awaaz ke liye)."""
    rider = request.user.rider_profile
    _touch(rider)
    visible = dispatch.visible_orders(_offers_qs(), rider, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES) if (rider.is_online and rider_gate.work_status(rider)[0]) else []
    active = DeliveryInfo.objects.filter(rider=rider, status__in=ACTIVE_STATUSES).count()
    assigned = DeliveryInfo.objects.filter(rider=rider, status='assigned').count()
    alerts = []
    if visible and shop_flag('rider_offer_alert_enabled') and shop_flag('rider_can_accept_orders'):
        for o in visible[:3]:      # full-screen alert: sab se purane 3 offers
            c = _offer_card(o, rider)
            alerts.append({
                'id': o.id, 'order_no': str(o.order_no), 'store': c['store'], 'store_addr': c['store_addr'],
                'cust_addr': c['cust_addr'], 'fee': f'{c["fee"]:,.0f}', 'is_cod': c['is_cod'],
                'total': f'{c["total"]:,.0f}', 'dist_km': c['dist_km'], 'items': c['items_count'],
                'accept_url': reverse('rider_accept_order', args=[o.id]),
                'decline_url': reverse('rider_decline_order', args=[o.id]),
            })
    return JsonResponse({'offers': len(visible), 'active': active, 'assigned': assigned, 'online': rider.is_online,
                         'offer_list': alerts, 'alert_seconds': dispatch.WINDOW_SECONDS})


@rider_login_required
@flag_required('rider_can_accept_orders', redirect_to='rider_home')
@require_POST
def rider_accept_order(request, pk):
    """Offer accept: jo pehle accept kare usay order milta hai."""
    rider = request.user.rider_profile
    if not rider.is_online:
        messages.error(request, '❌ Please go online first.')
        return redirect('rider_home')
    ok, why = rider_gate.work_status(rider)
    if not ok:
        messages.error(request, why)
        return redirect('rider_home')
    if DeliveryInfo.objects.filter(rider=rider, status__in=ACTIVE_STATUSES).count() >= MAX_ACTIVE_ORDERS:
        messages.error(request, f'❌ You already have {MAX_ACTIVE_ORDERS} orders. Please complete them first.')
        return redirect('rider_home')

    try:
        with transaction.atomic():
            order = (SaleOrder.objects.select_for_update().filter(pk=pk, status='ready')
                     .exclude(big_vehicle_state__in=['proposed', 'approved']).first())
            if not order:
                raise store_orders.OrderActionError('This order is no longer available.')
            if not dispatch.can_take(order, rider, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES):
                raise store_orders.OrderActionError('This order is being offered to another rider right now. Please check again shortly.')
            di, _ = DeliveryInfo.objects.select_for_update().get_or_create(sale_order=order)
            if di.rider_id and di.status != 'cancelled':
                raise store_orders.OrderActionError('This order was taken by another rider.')
            _assign(order, di, rider, request.user)
    except store_orders.OrderActionError as exc:
        messages.error(request, f'❌ {exc}')
        return redirect('rider_home')

    messages.success(request, f'✅ Order #{order.order_no} is yours. Now pick up the items from {store_orders.store_name(order.vendor_id)}.')
    return redirect('rider_home')


MAX_PROOF_BYTES = 8 * 1024 * 1024


def _clean_proof_photo(f):
    """Delivery photo check: sirf asli tasveer, 8 MB tak. Galat ho to OrderActionError."""
    if not f:
        return None
    if f.size > MAX_PROOF_BYTES:
        raise store_orders.OrderActionError('The photo is too large (max 8 MB).')
    try:
        from PIL import Image
        img = Image.open(f)
        img.verify()
        fmt = (img.format or '').upper()
        f.seek(0)
    except Exception:
        raise store_orders.OrderActionError('This file is not an image. Please take the photo again.')
    if fmt not in ('JPEG', 'PNG', 'WEBP', 'MPO'):
        raise store_orders.OrderActionError('Only JPG, PNG or WebP photos are allowed.')
    return f


UNASSIGN_REASONS = [('vehicle', 'Vehicle problem'), ('emergency', 'Emergency'),
                    ('far', 'Store is too far'), ('other', 'Other')]


@rider_login_required
@require_POST
def rider_order_action(request, pk, action):
    """action: arrived_store | store_issue | unassign | pickup | arrived_customer | deliver | fail | return"""
    rider = request.user.rider_profile
    if action not in ('arrived_store', 'store_issue', 'unassign', 'pickup', 'arrived_customer', 'deliver', 'fail', 'return'):
        messages.error(request, '❌ Invalid action.')
        return redirect('rider_home')

    try:
        with transaction.atomic():
            order = get_object_or_404(SaleOrder.objects.select_for_update(), pk=pk)
            di = get_object_or_404(DeliveryInfo, sale_order=order, rider=rider)
            cust = store_orders._customer_user(order)
            shop = store_orders.store_name(order.vendor_id)

            if action == 'arrived_store':
                if di.status != 'assigned' or order.status in ('cancelled', 'delivered'):
                    raise store_orders.OrderActionError('This order is no longer waiting for pickup.')
                if not di.arrived_store_at:
                    di.arrived_store_at = now()
                    di.save(update_fields=['arrived_store_at', 'updated_at'])
                    store_orders._notify(_vendor_user(order), f'🏍️ Rider arrived for #{order.order_no}',
                                         f'Rider {rider.name} is at the store. Please hand over the order.',
                                         '/shop/vendor/orders/', 'info', category='orders', priority='normal')
                messages.success(request, f'📍 Order #{order.order_no}: store knows you have arrived.')
            elif action == 'store_issue':
                from . import store_issues
                if order.status != 'ready':
                    raise store_orders.OrderActionError('This order is no longer active.')
                try:
                    from django.contrib.auth.models import User
                    store_issues.report(order, di, rider, request.POST.get('reason'), request.POST.get('note'),
                                        _vendor_user(order), User.objects.filter(is_superuser=True, is_active=True))
                except store_issues.IssueError as exc:
                    raise store_orders.OrderActionError(str(exc))
                messages.warning(request, f'⚠️ Order #{order.order_no}: the store was told. You can wait, '
                                          'or tap "Can\'t take this order" to give it back.')
            elif action == 'unassign':
                if di.status != 'assigned' or order.status != 'ready':
                    raise store_orders.OrderActionError('You can only give the order back before you pick it up.')
                reason = dict(UNASSIGN_REASONS).get(request.POST.get('reason'), 'Other')
                di.rider = None
                di.rider_name = di.rider_contact = di.rider_vehicle = None
                di.status = 'pending'
                di.assigned_at = None
                di.arrived_store_at = None
                di.peak_bonus = 0
                di.save()
                from . import store_issues
                store_issues.resolve(di)
                dispatch.release(order, rider)
                _track(order, 'ready_for_pickup', 'Rider changed',
                       'The rider could not take this order. We are finding another rider.', request.user, None)
                store_orders._notify(cust, f'🏍️ Finding a new rider for #{order.order_no}',
                                     'Your previous rider could not take the order. A new rider will be assigned shortly.',
                                     f'/shop/order/{order.id}/', 'info', category='orders')
                store_orders._notify(_vendor_user(order), f'↩️ Rider {rider.name} gave back #{order.order_no}',
                                     f'Reason: {reason}. The order is offered to other riders again.',
                                     '/shop/vendor/orders/?tab=active', 'warning', category='riders')
                messages.info(request, f'↩️ Order #{order.order_no} given back. It goes to other riders now.')
            elif action == 'arrived_customer':
                if di.status not in ('picked_up', 'in_transit') or order.status != 'ready':
                    raise store_orders.OrderActionError('Please tap "Picked up" first.')
                if not di.arrived_customer_at:
                    di.arrived_customer_at = now()
                    di.save(update_fields=['arrived_customer_at', 'updated_at'])
                    store_orders._notify(cust, f'🏍️ Your rider has arrived (#{order.order_no})',
                                         f'{rider.name} is at your door. Please be ready with the delivery code.',
                                         f'/shop/order/{order.id}/', 'info', category='orders', priority='high')
                messages.success(request, f'📍 Order #{order.order_no}: customer was told you have arrived.')
            elif action == 'pickup':
                if di.status != 'assigned' or order.status != 'ready':
                    raise store_orders.OrderActionError('This order is no longer ready for pickup.')
                if shop_flag('rider_pickup_code_required'):
                    from . import pickup_code
                    ok, why = pickup_code.check(order, request.POST.get('pickup_code'))
                    if not ok:
                        raise store_orders.OrderActionError(why)
                di.status = 'picked_up'
                di.picked_up_at = now()
                di.save()
                from . import store_issues
                store_issues.resolve(di)
                _track(order, 'out_for_delivery', 'Out for Delivery',
                       f'Rider {rider.name} picked up the order from {shop}.', request.user, rider)
                from . import whatsapp_auto
                whatsapp_auto.notify(order, 'pickup', rider=rider)
                store_orders._notify_event(cust, 'rider_on_way_customer',
                                           {'order_no': order.order_no, 'rider': rider.name},
                                           f'/shop/order/{order.id}/')
                messages.success(request, f'📦 Order #{order.order_no}: items picked up. Now go to the customer.')
            elif action in ('fail', 'return'):
                from . import delivery_returns
                if order.status != 'ready':
                    raise store_orders.OrderActionError('This order is no longer active.')
                try:
                    if action == 'fail':
                        delivery_returns.report(order, di, rider, request.POST.get('reason'), request.POST.get('note'))
                        messages.warning(request, f'⚠️ Order #{order.order_no}: problem reported. The customer was notified. '
                                                  'Wait for them, or return the order to the store after the waiting time.')
                    else:
                        delivery_returns.mark_returned(order, di, rider)
                        messages.success(request, f'↩️ Order #{order.order_no} returned to the store. Thank you.')
                except delivery_returns.ReturnError as exc:
                    raise store_orders.OrderActionError(str(exc))
            else:
                if di.status not in ('picked_up', 'in_transit') or order.status != 'ready':
                    raise store_orders.OrderActionError('Please tap "Picked up" first.')
                if shop_flag('rider_delivery_otp_required'):
                    from . import delivery_otp
                    ok, why = delivery_otp.check(order, request.POST.get('delivery_otp'))
                    if not ok:
                        raise store_orders.OrderActionError(why)
                proof = _clean_proof_photo(request.FILES.get('proof_photo'))
                if proof is None and shop_flag('rider_proof_photo_required'):
                    raise store_orders.OrderActionError('A delivery photo is required before marking the order as delivered.')
                if proof is not None:
                    di.delivery_photo = proof
                di.delivery_signature = (request.POST.get('receiver_name') or '').strip()[:100] or None
                total = store_orders.order_cash_due(order)
                is_cod = (order.payment_method or 'cod') == 'cod'
                di.status = 'delivered'
                di.delivered_at = now()
                di.rider_fee = Decimal(rider.per_delivery_fee or 0) + Decimal(di.peak_bonus or 0)
                di.cash_collected = total if is_cod else Decimal('0')
                di.delivery_notes = (f'COD cash collected by rider: Rs. {total:,.0f}' if is_cod
                                     else 'Online payment - no cash collected')
                di.save()
                from . import delivery_returns
                delivery_returns.close_open(di, 'delivered')
                store_orders.apply_vendor_action(order, 'delivered', user=request.user)
                _track(order, 'delivered', 'Delivered',
                       f'Rider {rider.name} delivered the order.', request.user, rider)
                store_orders._notify(_vendor_user(order), f'🎉 Order #{order.order_no} delivered',
                                     f'Rider {rider.name} delivered the order.'
                                     + (f' COD Rs. {total:,.0f} is with the rider.' if is_cod else ''),
                                     '/shop/vendor/orders/?tab=done', 'success', category='orders', priority='low')
                msg = tr(request, f'🎉 Order #{order.order_no} delivered. Earnings: Rs. {di.rider_fee:,.0f}.')
                if di.peak_bonus:
                    msg += ' ' + tr(request, f'🔥 Includes Rs. {di.peak_bonus:,.0f} peak bonus.')
                for kind, amt in _award_goal_bonuses(rider):
                    msg += ' ' + tr(request, f'🏆 {"Daily" if kind == "daily" else "Weekly"} goal completed! Bonus: Rs. {amt:,.0f}.')
                    store_orders._notify(request.user, '🏆 Goal bonus received',
                                         f'{"Daily" if kind == "daily" else "Weekly"} goal completed. You earned a Rs. {amt:,.0f} bonus.',
                                         reverse('rider_earnings'), 'success')
                if is_cod:
                    msg += ' ' + tr(request, f'Collected Rs. {total:,.0f} cash from the customer — please deposit it with the admin.')
                messages.success(request, msg)
    except store_orders.OrderActionError as exc:
        messages.error(request, f'❌ {exc}')
    return redirect('rider_home')


# ============================================
# VENDOR: rider chunna
# ============================================

@vendor_login_required
@flag_required('vendor_can_assign_riders', redirect_to='vendor_orders')
@require_POST
def vendor_assign_rider(request, pk):
    vendor = get_vendor_profile(request.user).vendor
    rider = get_object_or_404(RiderProfile, pk=request.POST.get('rider_id') or 0, is_active=True, approval_status='approved', rider_kind='bike')

    try:
        with transaction.atomic():
            order = get_object_or_404(SaleOrder.objects.select_for_update(), pk=pk, vendor=vendor)
            if order.status != 'ready':
                raise store_orders.OrderActionError('A rider can only be assigned to a "Ready" order.')
            di, _ = DeliveryInfo.objects.select_for_update().get_or_create(sale_order=order)
            if di.status in ('picked_up', 'in_transit', 'delivered'):
                raise store_orders.OrderActionError('The rider has already picked up the order, so it cannot be changed now.')
            _assign(order, di, rider, request.user)
            store_orders._notify_event(rider.user, 'rider_assigned',
                                       {'order_no': order.order_no, 'store': store_orders.store_name(order.vendor_id)},
                                       reverse('rider_home'), push_kind='rider')
    except store_orders.OrderActionError as exc:
        messages.error(request, f'❌ {exc}')
        return redirect(f"{reverse('vendor_orders')}?tab=active")

    messages.success(request, f'🏍️ Order #{order.order_no}: assigned to rider {rider.name}.')
    return redirect(f"{reverse('vendor_orders')}?tab=active")


# ============================================
# ADMIN: riders manage + hisab
# ============================================

def _support_n():
    from .rider_support import unread_for_admin
    return unread_for_admin()


def _admin_only(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.get_full_path()}")
        if not request.user.is_superuser:
            messages.error(request, '❌ Only the admin can manage riders.')
            return redirect('shop_home')
        return view(request, *args, **kwargs)
    return wrapper


def _money(raw):
    try:
        v = Decimal(str(raw).replace(',', '').strip())
    except (InvalidOperation, ValueError):
        return None
    return v.quantize(Decimal('0.01')) if v >= 0 else None


@_admin_only
def rider_manage(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            name = request.POST.get('name', '').strip()[:100]
            phone_raw = request.POST.get('phone', '').strip()[:20]
            password = request.POST.get('password', '')
            vehicle = request.POST.get('vehicle', '').strip()[:50]
            kind = 'big_vehicle' if request.POST.get('rider_kind') == 'big_vehicle' else 'bike'
            vehicle_no = ' '.join(request.POST.get('vehicle_no', '').split())[:30] if kind == 'big_vehicle' else ''
            fee = _money(request.POST.get('fee', '50'))
            if not name or not phone_raw or fee is None:
                messages.error(request, '❌ Enter name, phone, fee and password.')
            elif first_error(password, (name, phone_raw)):
                messages.error(request, '❌ ' + first_error(password, (name, phone_raw)))
            elif not is_valid_phone(phone_raw):
                messages.error(request, '❌ Phone number is not valid.')
            else:
                phone = normalize_phone(phone_raw)
                username = 'rider_' + phone.replace('+', '')
                try:
                    with transaction.atomic():
                        user = User.objects.create_user(username=username, password=password, first_name=name[:30])
                        RiderProfile.objects.create(user=user, name=name, phone=phone, vehicle=vehicle,
                                                    rider_kind=kind, vehicle_no=vehicle_no, per_delivery_fee=fee)
                    kind_txt = 'Big vehicle driver' if kind == 'big_vehicle' else 'Rider'
                    messages.success(request, f'✅ {kind_txt} {name} created. Login: {phone}')
                except IntegrityError:
                    messages.error(request, '❌ A rider with this phone already exists.')
        elif action == 'toggle':
            r = get_object_or_404(RiderProfile, pk=request.POST.get('rider_id') or 0)
            r.is_active = not r.is_active
            if not r.is_active:
                r.is_online = False
            r.save(update_fields=['is_active', 'is_online'])
            messages.success(request, f'{"✅ Activated" if r.is_active else "⏸️ Deactivated"}: {r.name}')
        elif action == 'password':
            r = get_object_or_404(RiderProfile, pk=request.POST.get('rider_id') or 0)
            pw = request.POST.get('password', '')
            if first_error(pw, (r.name, r.phone)):
                messages.error(request, '❌ ' + first_error(pw, (r.name, r.phone)))
            else:
                r.user.set_password(pw)
                r.user.save()
                messages.success(request, f'🔑 Password changed for {r.name}.')
        return redirect('rider_manage')

    riders = list(RiderProfile.objects.all())
    online_cut = now() - timedelta(minutes=2)
    for r in riders:
        r.open_count = r.deliveries.filter(status__in=ACTIVE_STATUSES).count()
        r.bal = rider_balances(r)
        r.live = bool(r.is_online and r.last_seen_at and r.last_seen_at >= online_cut)
        r.rating = rider_rating(r)
        r.pending_docs = r.documents.filter(status='pending').count()
        r.pending_payout = r.payout_requests.filter(status='pending').exists()
    from ..models import CustomerOTP, DeliveryFailure
    returns_n = DeliveryFailure.objects.filter(status__in=('waiting', 'returned')).count()
    from ..models import RiderSOS
    sos_n = RiderSOS.objects.filter(status='open').count()
    pending_resets = []
    by_phone = {r.phone: r for r in riders}
    for otp in CustomerOTP.objects.filter(purpose='rider_reset', is_used=False,
                                          expires_at__gt=now()).order_by('-created_at')[:20]:
        rider = by_phone.get(otp.phone)
        if rider and not otp.is_sent_to_customer:      # automatic nahi gaya -> manager ko bataana hai
            pending_resets.append({'rider': rider, 'code': otp.otp_code, 'expires_at': otp.expires_at})
    return render(request, 'customer_portal/rider/manage.html', {
        'pending_resets': pending_resets,
        'returns_n': returns_n,
        'sos_n': sos_n,
        'support_n': _support_n(),
        'riders': riders,
        'total_cash': sum((r.bal['cash_in_hand'] for r in riders), Decimal('0')),
        'total_due': sum((r.bal['due'] for r in riders), Decimal('0')),
    })


@_admin_only
def rider_detail(request, pk):
    rider = get_object_or_404(RiderProfile, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'fee':
            fee = _money(request.POST.get('fee'))
            if fee is None:
                messages.error(request, '❌ Fee is not valid.')
            else:
                rider.per_delivery_fee = fee
                rider.save(update_fields=['per_delivery_fee'])
                messages.success(request, f'✅ Fee set to Rs. {fee:,.0f} per delivery (applies to new orders).')
        elif action in ('req_paid', 'req_reject'):
            from . import rider_payouts
            try:
                rid = int(request.POST.get('request_id') or 0)
                if not rider.payout_requests.filter(pk=rid).exists():
                    raise rider_payouts.PayoutError('Request not found.')
                if action == 'req_paid':
                    req = rider_payouts.mark_paid(rid, request.user, request.POST.get('reference'))
                    messages.success(request, f'✅ Payout of Rs. {req.amount:,.0f} marked as paid ({rider.name}).')
                else:
                    rider_payouts.reject(rid, request.user, request.POST.get('reason'))
                    messages.success(request, 'Request rejected.')
            except (rider_payouts.PayoutError, ValueError) as exc:
                messages.error(request, f'❌ {exc}')
        elif action in ('cash_in', 'payout'):
            amount = _money(request.POST.get('amount'))
            bal = rider_balances(rider)
            limit = bal['cash_in_hand'] if action == 'cash_in' else bal['due']
            if not amount or amount <= 0:
                messages.error(request, '❌ Enter a valid amount.')
            elif amount > limit:
                messages.error(request, f'❌ Amount is too high. Maximum is Rs. {limit:,.0f}.')
            else:
                RiderSettlement.objects.create(rider=rider, kind=action, amount=amount,
                                               note=request.POST.get('note', '').strip()[:200],
                                               created_by=request.user)
                messages.success(request, f'✅ {"Cash deposited" if action == "cash_in" else "Earnings paid"}: Rs. {amount:,.0f} ({rider.name})')
        return redirect('rider_detail', pk=rider.pk)

    deliveries = (rider.deliveries.filter(status='delivered', sale_order__isnull=False)
                  .select_related('sale_order').order_by('-delivered_at')[:30])
    return render(request, 'customer_portal/rider/detail.html', {
        'r': rider, 'b': rider_balances(rider), 'deliveries': deliveries,
        'rating': rider_rating(rider),
        'reviews': rider.reviews.filter(rider_rating__isnull=False).select_related('sale_order')[:10],
        'settlements': rider.settlements.select_related('created_by')[:30],
        'payout_requests': list(rider.payout_requests.all()[:15]),
    })
