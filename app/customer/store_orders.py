"""
Step 2 - Multi-vendor cart aur vendor ke orders.

Is file mein 2 hisse hain:

A) CART RULES  (customer side)
   - cart mein ek waqt ek hi store ka maal (store = vendor, ya vendor_id=0 matlab shop ka apna maal)
   - store ki delivery fee, minimum order aur open/closed checkout mein lagte hain

B) VENDOR ORDER ACTIONS  (vendor side)
   - naya order aane par vendor ko notification
   - Accept / Reject / Ready
   - Reject par customer ko wajah ke saath notification + refund note + doosre stores ke suggestions

Order ka status purane SaleOrder statuses se hi chalta hai (admin ka kaam waise hi chalta rahe):
    pending   -> vendor ke liye "New"
    confirmed -> Accepted (tayyar ho raha hai)
    ready     -> Ready (rider/customer ke liye tayyar)
    delivered -> Deliver ho gaya (vendor khud mark karta hai; cash mil gaya)
    cancelled -> Rejected (reject_reason ke saath)
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.utils.timezone import now

logger = logging.getLogger(__name__)

ZERO = Decimal('0.00')

# Vendor reject karte waqt in mein se wajah chunta hai
REJECT_REASONS = [
    ('out_of_stock', 'Item is out of stock'),
    ('store_busy', 'Store is very busy right now'),
    ('store_closed', 'Store is closing'),
    ('out_of_area', 'We do not deliver to your area'),
    ('price_issue', 'Item price or details are wrong'),
    ('other', 'Other reason'),
]
REJECT_REASON_LABELS = dict(REJECT_REASONS)

# vendor action -> (status se, status par, naya status)
ACTIONS = {
    'accept': (('pending',), 'confirmed'),
    'reject': (('pending',), 'cancelled'),
    'ready': (('confirmed', 'processing'), 'ready'),
    'delivered': (('ready',), 'delivered'),
    # system action: vendor ne waqt par jawab nahi diya -> order khud cancel (user=None)
    'expire': (('pending',), 'cancelled'),
}


# ============================================================
# A) CART RULES
# ============================================================

def _vendor_ids_in_cart(cart):
    """Cart ke items kin stores ke hain. 0 = shop ka apna maal. Purane session items (vendor_id ke baghair) DB se."""
    ids = set()
    missing = []
    for item in (cart or {}).values():
        if 'vendor_id' in item:
            ids.add(int(item.get('vendor_id') or 0))
        elif item.get('product_id'):
            missing.append(item['product_id'])
    if missing:
        from ..models import Product
        for vid in Product.objects.filter(pk__in=missing).values_list('vendor_id', flat=True):
            ids.add(int(vid or 0))
    return ids


def cart_store_id(cart):
    """Cart ka store id (0 = shop). Cart khali ho to None."""
    ids = _vendor_ids_in_cart(cart)
    return sorted(ids)[0] if ids else None


def get_store_profile(vendor_id):
    """vendor_id ka VendorProfile (ya None: shop ka apna maal / profile nahi)."""
    if not vendor_id:
        return None
    from ..models import VendorProfile
    return VendorProfile.objects.filter(vendor_id=vendor_id).first()


def store_name(vendor_id):
    """Customer ko dikhane wala store ka naam."""
    prof = get_store_profile(vendor_id)
    if prof:
        return prof.business_name
    from ..models import CompanyInfo
    company = CompanyInfo.objects.first()
    return company.name if company else 'Shop'


def cart_store_rules(cart, subtotal):
    """
    Cart ke store ke qaide: delivery fee, minimum order, open/closed.

    Shop ke apne maal (vendor_id=0) par kuch nahi lagta - purana delivery system chalta hai.
    """
    ids = _vendor_ids_in_cart(cart)
    vendor_id = sorted(ids)[0] if ids else 0
    prof = get_store_profile(vendor_id)
    subtotal = Decimal(str(subtotal or 0))
    rules = {
        'vendor_id': vendor_id,
        'is_vendor_store': prof is not None,
        'mixed': len(ids) > 1,
        'profile': prof,
        'name': prof.business_name if prof else store_name(0),
        'delivery_fee': ZERO,
        'min_order': ZERO,
        'min_ok': True,
        'short_by': ZERO,
        'is_open': True,
        'closed_message': '',
        'time_text': '',
        'distance_km': None,
        'area_extra': ZERO,
        'out_of_range': False,
        'range_message': '',
        'fee_dynamic': False,
    }
    if prof is None:
        return rules

    min_order = Decimal(prof.min_order_amount or 0)
    from . import delivery_pricing
    q = delivery_pricing.quote(prof)
    rules.update({
        'delivery_fee': q['fee'],
        'distance_km': q['distance_km'],
        'area_extra': q['area_extra'],
        'out_of_range': q['out_of_range'],
        'range_message': q['message'],
        'fee_dynamic': q['dynamic'],
        'min_order': min_order,
        'min_ok': subtotal >= min_order,
        'short_by': max(min_order - subtotal, ZERO),
        'is_open': prof.is_open_now,
        'time_text': prof.eff_time_text,
    })
    if not prof.is_open_now:
        rules['closed_message'] = f'{prof.business_name} abhi band hai, baad mein order karein.'
    return rules


def vendor_delivery_info(rules):
    """calculate_delivery_charges jaisa dict, par store ki apni fee ke sath."""
    fee = rules['delivery_fee']
    return {
        'charges': fee,
        'type': 'standard',
        'time_estimate': rules['time_text'],
        'message': (f"🚚 {rules['name']} delivery" +
                    (f" · {rules['distance_km']} km" if rules.get('distance_km') is not None else '')),
        'is_free': fee <= 0,
    }


def vendor_delivery_options(rules):
    info = vendor_delivery_info(rules)
    return [{
        'type': 'standard',
        'label': f"🚚 {rules['name']} Delivery",
        'charges': info['charges'],
        'time': info['time_estimate'],
        'is_free': info['is_free'],
        'is_default': True,
    }]


# ------------------------------------------------------------
# SCHEDULED ORDERS (baad ke waqt ke liye order)
# ------------------------------------------------------------
SCHEDULE_MIN_MINUTES = 30      # kam az kam itne minute baad ka waqt
SCHEDULE_MAX_DAYS = 7          # zyada se zyada itne din aage
SCHEDULE_LEAD_MINUTES = 60     # vendor ke accept ki ghari waqt se itne minute pehle shuru hoti hai
SCHEDULE_SESSION_KEY = 'scheduled_for'


def parse_schedule(raw):
    """datetime-local '2026-11-10T19:30' (ya ISO) -> aware datetime. Khali -> None. Kharab -> ValueError."""
    from datetime import datetime
    from django.utils import timezone
    raw = (raw or '').strip()
    if not raw:
        return None
    dt = datetime.fromisoformat(raw)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def session_schedule(session):
    """Session mein rakha hua schedule (aware datetime) ya None."""
    try:
        return parse_schedule(session.get(SCHEDULE_SESSION_KEY))
    except (ValueError, TypeError):
        return None


def _within_hours_at(prof, local_dt):
    """local_dt = aware local datetime (din ke hisab se waqt dekhna hai)."""
    return prof.within_hours_at(local_dt)


def schedule_error(cart, when, subtotal=0):
    """Schedule ka waqt theek na ho to message (str), warna None."""
    from django.utils import timezone
    n = now()
    if when < n + timedelta(minutes=SCHEDULE_MIN_MINUTES):
        return f'Schedule ka waqt kam az kam {SCHEDULE_MIN_MINUTES} minute baad ka chunein.'
    if when > n + timedelta(days=SCHEDULE_MAX_DAYS):
        return f'Schedule {SCHEDULE_MAX_DAYS} din se zyada aage ka nahi ho sakta.'
    rules = cart_store_rules(cart, subtotal)
    prof = rules.get('profile')
    if rules.get('is_vendor_store') and prof:
        if prof.store_status == 'closed':
            return f"{rules['name']} abhi band hai, schedule order nahi ho sakta."
        local_when = timezone.localtime(when)
        if not _within_hours_at(prof, local_when):
            day = prof.DAY_NAMES[local_when.weekday()]
            return (f"{rules['name']} us waqt band hoga. {day} ko khulne ka waqt: "
                    f"{prof.hours_text_for(local_when)}.")
    return None


def validate_cart_for_order(cart, subtotal, scheduled_for=None):
    """Order se pehle check. Masla ho to message (str) lautata hai, theek ho to None.
    scheduled_for dein to store ke abhi khule hone ki shart nahi, schedule ke waqt ki jaanch hoti hai."""
    rules = cart_store_rules(cart, subtotal)
    if rules['mixed']:
        return 'Your cart has items from different stores. Empty the cart and order from one store.'
    if scheduled_for is not None:
        err = schedule_error(cart, scheduled_for, subtotal)
        if err:
            return err
    if rules['is_vendor_store']:
        if rules.get('out_of_range'):
            return rules['range_message']
        if scheduled_for is None and not rules['is_open']:
            return rules['closed_message']
        from .item_schedule import cart_error      # item schedule (scheduled order ho to us waqt ke hisaab se)
        sched_err = cart_error(cart, scheduled_for)
        if sched_err:
            return sched_err
        if not rules['min_ok']:
            return (f"{rules['name']} ka minimum order Rs. {rules['min_order']:,.0f} hai. "
                    f"Aur Rs. {rules['short_by']:,.0f} ka maal add karein.")
    return None


def store_order_fields(cart, cart_data, payment_method):
    """SaleOrder.objects.create(...) mein lagane wali store ki fields."""
    rules = cart_data.get('store') or cart_store_rules(cart, cart_data.get('subtotal', 0))
    prof = rules.get('profile')
    return {
        'vendor': prof.vendor if prof else None,
        'delivery_fee': cart_data.get('delivery_charges') or ZERO,
        'payment_method': payment_method or '',
    }


# ------------------------------------------------------------
# STOCK LOCK  (overselling roknay ke liye)
# ------------------------------------------------------------
# Jin orders ka maal abhi tak invoice (stock kam) nahi hua, magar customer ko de diya gaya hai.
OPEN_ORDER_STATUSES = ('pending', 'confirmed', 'processing', 'ready')


def check_and_lock_stock(cart, warehouse):
    """
    Order se pehle stock check + lock. Sirf transaction.atomic ke ANDAR chalayein.

    - Cart ke har product ki Inventory row select_for_update se lock hoti hai (product_id ki
      tarteeb mein, taake do orders aapas mein deadlock na karein). Lock transaction ke aakhir
      tak rehta hai, yani doosra customer tab tak intezar karta hai jab tak pehla order ban jaye.
    - Available = stock - admin reserved_stock - un khule web orders ki qty jo abhi invoice nahi
      hue (stock invoice par kam hota hai, is liye pending orders alag se ginay jate hain).
    - Cart mein ek product kayi baar ho to qty jama karke check hoti hai.

    Return: None (sab theek) ya error text (customer ko dikhane ke liye).
    """
    from django.db.models import Sum
    from ..models import Inventory, SaleOrderItem

    need = {}
    names = {}
    for item in (cart or {}).values():
        pid = item['product_id']
        need[pid] = need.get(pid, 0) + item['quantity']
        names.setdefault(pid, item.get('name') or f'#{pid}')

    pids = sorted(need)
    locked = {
        inv.product_id: inv
        for inv in Inventory.objects.select_for_update()
        .filter(warehouse=warehouse, product_id__in=pids).order_by('product_id')
    }

    for pid in pids:
        inv = locked.get(pid)
        stock = (inv.stock or 0) if inv else 0
        reserved = (inv.reserved_stock or 0) if inv else 0
        # reserved=True wali items already reserved_stock mein hain: double count na karein
        committed = SaleOrderItem.objects.filter(
            order__warehouse=warehouse, product_id=pid, reserved=False,
            order__status__in=OPEN_ORDER_STATUSES, order__converted_to_sale__isnull=True,
        ).aggregate(t=Sum('qty'))['t'] or 0
        available = stock - reserved - committed
        if need[pid] > available:
            return f'Not enough stock for {names[pid]}. Available: {max(0, int(available))}'
    return None


# ============================================================
# B) VENDOR ORDER ACTIONS
# ============================================================

def order_payable_total(order):
    """Items + delivery fee - discount."""
    return order.total_after_discount() + (order.delivery_fee or ZERO)


def order_cash_due(order):
    """Customer se asal mein kitni raqam leni hai: total - wallet se ada hui raqam (rider COD yahi leta hai)."""
    return max(order_payable_total(order) - (getattr(order, 'wallet_paid', None) or ZERO), ZERO)


def _notify(user, title, message, link=None, kind='info', push_kind=None, push_actions=None,
            category='sales', priority='normal'):
    if not user:
        return
    try:
        from ..models import Notification
        Notification.send(user=user, title=title, message=message,
                          notification_type=kind, category=category, link=link,
                          push_kind=push_kind, push_actions=push_actions, priority=priority)
    except Exception as exc:  # notification se order kabhi na rukey
        logger.error("Notification error: %s", exc)


def _notify_event(user, event, ctx=None, link=None, push_kind=None, push_actions=None, **overrides):
    """Template wali notification (app/utils/notification_rules.py). Order kabhi nahi rukta: error sirf log hota hai."""
    if not user:
        return None
    try:
        from ..models import Notification
        return Notification.notify(event, user, ctx, link=link, push_kind=push_kind,
                                   push_actions=push_actions, **overrides)
    except Exception as exc:
        logger.error("Notification error (%s): %s", event, exc)
        return None


def _notify_admin_event(event, ctx=None, link=None, **overrides):
    try:
        from ..utils.admin_alerts import notify_admins
        notify_admins(event, ctx, link=link, **overrides)
    except Exception as exc:
        logger.error("Admin notification error (%s): %s", event, exc)


def _customer_user(order):
    portal = getattr(order.customer, 'portal_profile', None)
    return getattr(portal, 'user', None)


def notify_vendor_new_order(order):
    """Naya order aane par vendor ko in-app notification (vendor dashboard/navbar mein)."""
    if not order.vendor_id:
        return
    prof = get_store_profile(order.vendor_id)
    if not prof:
        return
    from . import whatsapp_auto
    whatsapp_auto.notify(order, 'placed')
    if try_auto_accept(order, prof):
        return
    items = order.items.count()
    when = ''
    if getattr(order, 'scheduled_for', None):
        from django.utils import timezone
        when = f"\n⏰ Schedule: {timezone.localtime(order.scheduled_for).strftime('%d %b, %I:%M %p')}"
    from .vendor_access import notify_users
    for target in notify_users(prof):          # owner (branch ho to us ka owner) + active staff
        _notify(
            target,
            f'🛒 New order #{order.order_no}' + (' (scheduled)' if when else '') + (f' [{prof.branch_name}]' if prof.parent_id else ''),
            (f'{order.customer.name} - {items} item(s)\n'
             f'Total: Rs. {order_payable_total(order):,.0f}{when}\n'
             f'Open the dashboard to Accept or Reject.'),
            link='/shop/vendor/orders/',
            kind='sale',
            category='orders', priority='high',
            push_kind='vendor',
            push_actions=_vendor_buttons(target, order),     # notification se seedha Accept / Reject
        )
        _start_reminders(order, target)


def try_auto_accept(order, prof):
    """Store ne auto-accept chalu kiya ho to naya order khud qubool. True = ho gaya (ringtone/reminders ki zaroorat nahi).
    Koi bhi galti ho to False: order normal tareeqe se vendor ke paas jata hai (kabhi order nahi rukta)."""
    if not getattr(prof, 'auto_accept', False) or order.status != 'pending':
        return False
    try:
        from django.db import transaction
        from ..models import SaleOrder
        with transaction.atomic():
            locked = SaleOrder.objects.select_for_update().get(pk=order.pk)
            if locked.status != 'pending':
                return False
            apply_vendor_action(locked, 'accept', user=prof.user,
                                prep_minutes=prof.auto_accept_prep_minutes or None)
        order.status = locked.status
        order.prep_minutes = locked.prep_minutes
        from .vendor_access import notify_users
        for target in notify_users(prof):
            _notify(target, f'✅ Order #{order.order_no} auto-accepted' + (f' [{prof.branch_name}]' if prof.parent_id else ''),
                    f'{order.customer.name} - Rs. {order_payable_total(order):,.0f}\n'
                    'Auto-accept is on. Tap Ready when the order is prepared.',
                    link='/shop/vendor/orders/?tab=active', kind='sale', category='orders')   # push_kind nahi: auto-accept par ring nahi bajni chahiye
        return True
    except Exception as exc:
        logger.error('Auto-accept error (order %s): %s', getattr(order, 'pk', '?'), exc)
        return False


def _vendor_buttons(user, order):
    try:
        from .push_actions import vendor_buttons
        return vendor_buttons(user, order)
    except Exception as exc:
        logger.error('vendor_buttons error: %s', exc)
        return None


def _start_reminders(order, user):
    try:
        from .push_actions import schedule_vendor_reminders
        schedule_vendor_reminders(order, user)
    except Exception as exc:
        logger.error('reminders error: %s', exc)


def whatsapp_link(phone, text):
    """wa.me link (khud send nahi hota - vendor click karke bhejta hai)."""
    try:
        from ..whatsapp_utils import WhatsAppSender
        res = WhatsAppSender.send_direct_message(phone, text)
        return res.get('url') if res.get('success') else None
    except Exception:
        return None


def customer_whatsapp_text(order, action):
    shop = store_name(order.vendor_id)
    if action == 'accept':
        eta = f" Taqreeban {order.prep_minutes} minute mein tayyar hoga." if order.prep_minutes else ''
        return f"✅ {shop}: Aap ka order #{order.order_no} qubool ho gaya.{eta}"
    if action == 'ready':
        return f"📦 {shop}: Aap ka order #{order.order_no} tayyar hai."
    if action == 'delivered':
        return f"🎉 {shop}: Aap ka order #{order.order_no} deliver ho gaya. Shukriya!"
    if action in ('reject', 'expire'):
        return (f"❌ {shop}: Maazrat, order #{order.order_no} qubool nahi ho saka. "
                f"Wajah: {order.reject_reason}")
    return ''


def suggest_other_stores(order, limit=3):
    """
    Reject hone par naye stores: wahi category ka maal bechne wale, abhi khule hue.
    Pehle same category wale, phir koi bhi khula store.
    """
    from ..models import Product, VendorProfile

    live = Product.objects.filter(is_active=True, approval_status='approved', vendor__isnull=False)
    base = VendorProfile.objects.filter(
        is_approved=True, vendor__in=live.values('vendor')
    ).exclude(vendor_id=order.vendor_id).select_related('vendor').prefetch_related('day_hours')

    cat_ids = list(
        Product.objects.filter(saleorderitem__order=order)
        .exclude(category__isnull=True).values_list('category_id', flat=True).distinct()
    )
    picked, seen = [], set()
    if cat_ids:
        same = base.filter(vendor__in=live.filter(category_id__in=cat_ids).values('vendor'))
        for prof in same:
            if prof.is_open_now and prof.pk not in seen:
                picked.append(prof)
                seen.add(prof.pk)
    if len(picked) < limit:
        for prof in base:
            if prof.is_open_now and prof.pk not in seen:
                picked.append(prof)
                seen.add(prof.pk)
    return picked[:limit]


def refund_note(order):
    """Reject par paisa ka message. COD mein kuch kata hi nahi hota."""
    if (order.payment_method or 'cod') == 'cod':
        return 'It was Cash on Delivery, so no money was taken from you.'
    return ('You paid online, so the full amount will be refunded. '
            'If there is a problem with the refund, please contact us.')


class OrderActionError(Exception):
    """Vendor ke action mein masla (galat status, wajah nahi di, ...). Message customer-friendly hota hai."""


def clean_reject_reason(code, note):
    """Chuni hui wajah + optional note -> customer ko dikhane wala text (max 200 chars)."""
    code = (code or '').strip()
    label = REJECT_REASON_LABELS.get(code)
    note = (note or '').strip()
    if not label:
        raise OrderActionError('Choose a reason for rejecting.')
    if code == 'other':
        if not note:
            raise OrderActionError('If you choose "Other reason", please write the reason.')
        return note[:200]
    return (f'{label}. {note}' if note else label)[:200]


def apply_vendor_action(order, action, *, user, prep_minutes=None, reason_code='', reason_note=''):
    """
    Vendor ka action lagao. order select_for_update ke andar (transaction.atomic) hona chahiye.
    Nakaam hone par OrderActionError.
    """
    if action not in ACTIONS:
        raise OrderActionError('Invalid action.')
    allowed_from, new_status = ACTIONS[action]
    # Customer ne bari gari ka kiraya radd kiya: accept ho chuka order bhi cancel ho sakta hai
    if action == 'reject' and getattr(order, 'big_vehicle_state', '') == 'declined':
        allowed_from = tuple(allowed_from) + ('confirmed', 'processing')
    if action == 'ready' and getattr(order, 'big_vehicle_state', '') == 'proposed':
        raise OrderActionError('The customer has not approved the big vehicle fare yet. You can mark the order Ready only after approval.')
    if (action == 'ready' and getattr(order, 'big_vehicle_state', '') == 'approved'
            and getattr(order, 'big_vehicle_driver_id', None)
            and getattr(order, 'big_vehicle_driver_state', '') != 'accepted'):
        raise OrderActionError('The chosen vehicle driver has not accepted yet. Wait for the driver, or pick another vehicle / switch to manual.')
    if order.status not in allowed_from:
        raise OrderActionError(
            f'Order #{order.order_no} is now "{order.get_status_display()}", so this action is not possible.')

    if action == 'reject':
        order.reject_reason = clean_reject_reason(reason_code, reason_note)
    if action == 'accept':
        deadline = accept_deadline(order)
        if deadline and now() > deadline:
            raise OrderActionError(
                f'The time to respond to order #{order.order_no} ({accept_timeout_minutes()} minutes) is over. '
                'The order is being cancelled automatically.')
        if prep_minutes:
            order.prep_minutes = prep_minutes
    if action == 'expire':
        order.reject_reason = f'Store ne {accept_timeout_minutes()} minute mein jawab nahi diya.'[:200]

    order.status = new_status
    if action != 'expire':          # expire par vendor_responded_at khali rehta hai (miss hua order)
        order.vendor_responded_at = now()
    if action == 'accept':          # performance dashboard: asal accept / ready ka waqt
        order.accepted_at = now()
    elif action == 'ready':
        order.ready_at = now()
    order.save()
    if action == 'delivered':
        auto_invoice_delivered(order, user)
    after_vendor_action(order, action, user)


def auto_invoice_delivered(order, user):
    """
    Delivered hote hi invoice (Sale) khud bana do, poora PAID (COD cash mil chuka / online pehle ada).
    Is se vendor dashboard ki sales/commission bharti hain, stock kam hota hai aur accounts ban jate hain.
    Kuch bhi fail ho (stock kam, month locked...) to delivery na ruke: order Delivered hi rehta hai
    aur admin ko notification milti hai ke manually invoice banaye.
    """
    from django.db import transaction
    from ..models import Sale, SaleItem
    from ..vendor_commission import option_sale_item_fields

    if order.converted_to_sale_id:
        return None
    try:
        with transaction.atomic():
            sale = Sale.objects.create(
                warehouse=order.warehouse,
                customer=order.customer,
                bill_no=f"INV-{order.order_no}",
                sale_date=now(),
                paid=Decimal('0.00'),
                discount_value=order.discount_value,
                created_by=user,
            )
            for item in order.items.all():
                SaleItem.objects.create(sale=sale, product=item.product, qty=item.qty, price=item.price,
                                        **option_sale_item_fields(item))
            # Poora paid: items ki raqam customer ne (COD cash / online) de di hai
            sale.paid = sale.total_amount()
            sale.save()
            order.status = 'invoiced'
            order.converted_to_sale = sale
            order.save()
        return sale
    except Exception as exc:
        logger.error("Auto invoice failed for order %s: %s", order.order_no, exc)
        try:
            from django.contrib.auth.models import User
            for admin in User.objects.filter(is_superuser=True, is_active=True):
                _notify(admin, f'⚠️ Order #{order.order_no} ka invoice khud nahi bana',
                        f'Wajah: {exc}\nOrder Delivered hai, manually "Convert to Invoice" karein.',
                        f'/orders/sale/{order.id}/', 'warning')
        except Exception:
            pass
        return None


def after_vendor_action(order, action, user):
    """Customer (aur reject par admin) ko batao."""
    link = f'/shop/order/{order.id}/'
    cust_user = _customer_user(order)
    shop = store_name(order.vendor_id)

    from . import whatsapp_auto
    whatsapp_auto.notify(order, action)      # WhatsApp (settings mein on ho to); ghalti order nahi rokti

    def _status(emoji, status_text, detail, kind):
        _notify_event(cust_user, 'order_status_customer',
                      {'order_no': order.order_no, 'emoji': emoji, 'status_text': status_text,
                       'store': shop, 'detail': detail}, link, notification_type=kind)

    if action == 'accept':
        eta = f' Ready in about {order.prep_minutes} minutes.' if order.prep_minutes else ''
        _status('✅', 'accepted', f'{shop} accepted your order.{eta}', 'success')
    elif action == 'ready':
        if getattr(order, 'big_vehicle_state', '') == 'approved':
            _status('📦', 'is ready', f'Your order is prepared. The store will send it with the {order.big_vehicle_type or "big vehicle"}.', 'info')
        else:
            _status('📦', 'is ready', 'Your order is prepared and waiting for the rider.', 'info')
    elif action == 'delivered':
        _status('🎉', 'delivered', 'Your order has arrived. Enjoy!', 'success')
        try:
            from django.contrib.auth.models import User
            for admin in User.objects.filter(is_superuser=True, is_active=True):
                _notify(admin, f'✅ Order #{order.order_no} delivered',
                        f'{shop} marked the order delivered. Rs. {order_payable_total(order):,.0f} '
                        f'({(order.payment_method or "cod").upper()}). '
                        + ('Invoice created automatically.' if order.converted_to_sale_id else 'You can create the invoice now.'),
                        f'/orders/sale/{order.id}/', 'success', category='orders', priority='low')
        except Exception as exc:
            logger.error("Delivered notify error: %s", exc)
    elif action in ('reject', 'expire'):
        if action == 'expire':
            _notify_event(cust_user, 'order_cancelled_customer',
                          {'order_no': order.order_no, 'store': shop,
                           'reason': 'The store did not respond in time. You can order from another store.',
                           'refund_note': refund_note(order)}, link)
            prof = get_store_profile(order.vendor_id)
            _notify_event(getattr(prof, 'user', None), 'order_missed_vendor',
                          {'order_no': order.order_no, 'minutes': accept_timeout_minutes()},
                          '/shop/vendor/orders/?tab=done')
        else:
            _notify_event(cust_user, 'order_cancelled_customer',
                          {'order_no': order.order_no, 'store': shop,
                           'reason': f'The store could not accept your order. Reason: {order.reject_reason}',
                           'refund_note': refund_note(order)}, link)
        # Online payment ho to admin ko refund yaad dilao
        if (order.payment_method or 'cod') != 'cod':
            _notify_admin_event('refund_due',
                                {'order_no': order.order_no, 'store': shop,
                                 'reason': order.reject_reason or ('no response' if action == 'expire' else 'rejected'),
                                 'method': order.payment_method,
                                 'total': f'Rs. {order_payable_total(order):,.0f}'},
                                link=f'/orders/sale/{order.id}/')



# ============================================================
# C) AUTO-EXPIRE (Talabat jaisa): vendor waqt par jawab na de to order cancel
# ============================================================

EXPIRE_THROTTLE_KEY = 'store_orders:expire_last_run'


def accept_timeout_minutes():
    """settings.VENDOR_ACCEPT_TIMEOUT_MINUTES (default 5). 0 = auto-expire band."""
    try:
        minutes = int(getattr(settings, 'VENDOR_ACCEPT_TIMEOUT_MINUTES', 5))
    except (TypeError, ValueError):
        minutes = 5
    return max(minutes, 0)


def accept_deadline(order):
    """Store order ke jawab ki aakhri waqt; baghair deadline wale order (shop ka apna, pending nahi, band) par None."""
    minutes = accept_timeout_minutes()
    if not minutes or not order.vendor_id or order.status != 'pending' or not order.created_at:
        return None
    start = order.created_at
    sched = getattr(order, 'scheduled_for', None)
    if sched:       # schedule order: ghari waqt se thora pehle shuru hoti hai
        start = max(start, sched - timedelta(minutes=SCHEDULE_LEAD_MINUTES))
    return start + timedelta(minutes=minutes)


def expire_unaccepted_orders(order_id=None):
    """
    Jin store orders ko vendor ne waqt par accept/reject nahi kiya unhein cancel karo
    (customer, vendor aur online payment mein admin ko notification ke saath).
    order_id dein to sirf wahi order check hota hai. Wapas: kitne order expire hue.
    """
    from django.db import transaction
    from ..models import SaleOrder

    minutes = accept_timeout_minutes()
    if not minutes:
        return 0
    cutoff = now() - timedelta(minutes=minutes)
    from django.db.models import Q
    due = SaleOrder.objects.filter(status='pending', vendor__isnull=False, created_at__lte=cutoff).filter(
        Q(scheduled_for__isnull=True)
        | Q(scheduled_for__lte=cutoff + timedelta(minutes=SCHEDULE_LEAD_MINUTES)))
    if order_id is not None:
        due = due.filter(pk=order_id)
    expired = 0
    for oid in list(due.values_list('id', flat=True)[:200]):
        try:
            with transaction.atomic():
                order = SaleOrder.objects.select_for_update().get(pk=oid)
                if order.status != 'pending':      # is dauran vendor ne jawab de diya
                    continue
                apply_vendor_action(order, 'expire', user=None)
                expired += 1
        except Exception as exc:
            logger.error("Order expire failed for %s: %s", oid, exc)
    return expired


def expire_if_due(throttle_seconds=15):
    """
    Cron ke baghair bhi chale: vendor/customer pages khulne par check (har ~15 second mein ek baar).
    Cron/command (expire_orders) laga hua ho to ye sirf extra hifazat hai.
    """
    try:
        if not cache.add(EXPIRE_THROTTLE_KEY, 1, throttle_seconds):
            return 0
    except Exception:
        pass
    return expire_unaccepted_orders() + expire_big_vehicle_proposals()


# ============================================
# BARI GARI (bhaari order): store kiraya likhta hai, customer manzoor karta hai
# Customer ko dikhne wale saare message English mein hain (Urdu app/i18n/portal_messages.py se aata hai).
# ============================================
BIG_VEHICLE_MAX_FEE = Decimal('1000000')      # admin setting big_vehicle_max_fee na ho to yeh hadd


def _bv_setting(name, default):
    """Admin ki Settings > Shop se raqam; khali ya galat ho to default."""
    from .offers import setting_decimal
    return setting_decimal(name, str(default))


def big_vehicle_max_fee():
    value = _bv_setting('big_vehicle_max_fee', BIG_VEHICLE_MAX_FEE)
    return value if value > 0 else BIG_VEHICLE_MAX_FEE


def big_vehicle_max_offers():
    """Ek order par store kitni dafa kiraya bhej sakta hai (kam az kam 1)."""
    try:
        return max(int(_bv_setting('big_vehicle_max_offers', 3)), 1)
    except (TypeError, ValueError):
        return 3


def big_vehicle_timeout_minutes():
    """Customer ke jawab ki muddat: admin setting big_vehicle_response_minutes, warna settings.BIG_VEHICLE_RESPONSE_TIMEOUT_MINUTES (120). 0 = band."""
    try:
        default = int(getattr(settings, 'BIG_VEHICLE_RESPONSE_TIMEOUT_MINUTES', 120))
    except (TypeError, ValueError):
        default = 120
    try:
        return max(int(_bv_setting('big_vehicle_response_minutes', default)), 0)
    except (TypeError, ValueError):
        return max(default, 0)


def big_vehicle_deadline(order):
    """Customer ke jawab ki aakhri waqt (datetime); intezar mein na ho ya timeout band ho to None."""
    minutes = big_vehicle_timeout_minutes()
    if (not minutes or getattr(order, 'big_vehicle_state', '') != 'proposed'
            or not getattr(order, 'big_vehicle_proposed_at', None)):
        return None
    return order.big_vehicle_proposed_at + timedelta(minutes=minutes)


def _big_vehicle_deadline_text():
    minutes = big_vehicle_timeout_minutes()
    if not minutes:
        return ''
    if minutes % 60 == 0:
        hours = minutes // 60
        span = f'{hours} hour' if hours == 1 else f'{hours} hours'
    else:
        span = f'{minutes} minutes'
    return f' You have {span} to respond, otherwise the order is cancelled automatically.'


def big_vehicle_total_preview(order, fee):
    """Kiraya manzoor hone par order ka naya total (items - discount + kiraya)."""
    return order.total_after_discount() + (fee or ZERO)


def big_vehicle_max_jobs():
    """Ek gari ek waqt mein kitne orders par lag sakti hai (double booking se bachao). Admin setting big_vehicle_max_jobs, default 1."""
    try:
        return max(int(_bv_setting('big_vehicle_max_jobs', 1)), 1)
    except (TypeError, ValueError):
        return 1


_BV_LIVE_STATES = ('proposed', 'approved')
_BV_LIVE_STATUSES = ('confirmed', 'processing', 'ready')


def _bv_busy_counts(driver_ids, exclude_order_id=None):
    """{driver_id: kitne maujooda jobs} (customer ke jawab ka intezar ya manzoor, jab tak deliver / cancel na ho)."""
    from django.db.models import Count
    from ..models import SaleOrder
    qs = SaleOrder.objects.filter(big_vehicle_driver__in=list(driver_ids), big_vehicle_state__in=_BV_LIVE_STATES,
                                  status__in=_BV_LIVE_STATUSES)
    if exclude_order_id:
        qs = qs.exclude(pk=exclude_order_id)
    return {r['big_vehicle_driver']: r['n'] for r in qs.values('big_vehicle_driver').annotate(n=Count('id'))}


def big_vehicle_choices(store_lat=None, store_lng=None):
    """Store ke liye gari ki list (rider ki tarah). Sort: online pehle, phir khali gari, phir store se nazdeek, phir behtar rating.
    Har item: id, name, phone, vehicle (qism), vehicle_no, live, busy (maujooda jobs), full (ab aur job nahi le sakti),
    dist_km (seedha fasla, ya None), rating (avg ya None), rating_n."""
    from django.db.models import Avg, Count
    from ..models import OrderReview, RiderProfile
    from . import dispatch
    t = now()
    max_jobs = big_vehicle_max_jobs()
    qs = (RiderProfile.objects.filter(is_active=True, approval_status='approved', rider_kind='big_vehicle')
          .annotate(push_n=Count('user__fcm_devices', distinct=True)))
    drivers = list(qs)
    ids = [r.id for r in drivers]
    busy = _bv_busy_counts(ids)
    ratings = {x['rider']: x for x in OrderReview.objects.filter(rider__in=ids, rider_rating__isnull=False)
               .values('rider').annotate(avg=Avg('rider_rating'), n=Count('id'))}
    rows = []
    for r in drivers:
        seen = r.last_seen_at
        live = bool(r.is_online and seen and (
            seen >= t - timedelta(seconds=dispatch.SEEN_FRESH_SECONDS)
            or (r.push_n and seen >= t - timedelta(seconds=dispatch.PUSH_REACHABLE_SECONDS))))
        dist = None
        if store_lat is not None and store_lng is not None:
            lat, lng = dispatch._rider_coords(r, t)
            if lat is not None:
                dist = round(dispatch.haversine_km(float(store_lat), float(store_lng), lat, lng), 1)
        rt = ratings.get(r.id)
        n_busy = busy.get(r.id, 0)
        rows.append({'id': r.id, 'name': r.name, 'phone': r.phone, 'vehicle': r.vehicle,
                     'vehicle_no': r.vehicle_no, 'live': live, 'busy': n_busy, 'full': n_busy >= max_jobs,
                     'dist_km': dist, 'rating': round(float(rt['avg']), 1) if rt else None,
                     'rating_n': rt['n'] if rt else 0})
    rows.sort(key=lambda x: (not x['live'], x['full'], x['dist_km'] if x['dist_km'] is not None else 1e9,
                             -(x['rating'] or 0), x['name'].lower()))
    return rows


def _pick_big_vehicle_driver(driver_id, order=None):
    """Store ne list se jo gari chuni usay check karo (active + approved + bari gari + khali). Khali id = manual.
    Driver ki row lock hoti hai, taake do store ek hi waqt mein ek gari na le len."""
    from ..models import RiderProfile
    try:
        did = int(driver_id or 0)
    except (TypeError, ValueError):
        did = 0
    if not did:
        return None
    drv = (RiderProfile.objects.select_for_update()
           .filter(pk=did, is_active=True, approval_status='approved', rider_kind='big_vehicle').first())
    if not drv:
        raise OrderActionError('This vehicle is not available anymore. Pick another one or enter it manually.')
    busy = _bv_busy_counts([drv.pk], exclude_order_id=getattr(order, 'pk', None)).get(drv.pk, 0)
    if busy >= big_vehicle_max_jobs():
        raise OrderActionError(f'{drv.name} is already busy with another order. Pick another vehicle or enter one manually.')
    return drv


def _notify_big_vehicle_driver(driver, title, message):
    if driver and driver.user_id:
        _notify(driver.user, title, message, link='/shop/rider/', kind='info', push_kind='rider',
                category='orders', priority='high')


def _close_big_vehicle_offer(order, outcome):
    """Intezar mein pade kiraye ki history row band karo (approved / declined / expired)."""
    from ..models import BigVehicleOffer
    BigVehicleOffer.objects.filter(order=order, outcome='proposed').update(
        outcome=outcome, responded_at=now())


def _notify_admins(title, message, link, kind='warning'):
    try:
        from django.contrib.auth.models import User
        for admin in User.objects.filter(is_superuser=True, is_active=True):
            _notify(admin, title, message, link, kind, category='orders')
    except Exception as exc:
        logger.error("Big vehicle admin notify error: %s", exc)


def propose_big_vehicle(order, *, vtype, fee, note='', user=None, driver_id=None):
    """Store bari gari ka kiraya bhejta hai (order accept hone ke baad). order select_for_update mein ho."""
    from ..models import BigVehicleOffer
    if order.status not in ('confirmed', 'processing'):
        raise OrderActionError('You can send the big vehicle fare only after accepting the order.')
    if getattr(order, 'big_vehicle_state', '') == 'approved':
        raise OrderActionError('The customer has already approved this fare.')
    driver = _pick_big_vehicle_driver(driver_id, order)
    vtype = ' '.join((vtype or (driver.vehicle if driver else '') or '').split())[:60]
    if not vtype:
        raise OrderActionError('Enter the vehicle type (for example Suzuki, Pickup, Loader).')
    try:
        fee = Decimal(str(fee)).quantize(Decimal('1'))
    except Exception:
        raise OrderActionError('Enter the fare as a number only.')
    max_fee = big_vehicle_max_fee()
    if fee <= 0 or fee > max_fee:
        raise OrderActionError(f'The fare must be more than 0 and not more than Rs. {max_fee:,.0f}.')
    max_offers = big_vehicle_max_offers()
    if BigVehicleOffer.objects.filter(order=order).count() >= max_offers:
        raise OrderActionError(f'You can send at most {max_offers} big vehicle fares for one order.')
    note = ' '.join((note or '').split())[:200]
    # Purana intezar mein pada kiraya (agar store naya bheje) history mein "superseded" ho jata hai
    BigVehicleOffer.objects.filter(order=order, outcome='proposed').update(
        outcome='superseded', responded_at=now())
    BigVehicleOffer.objects.create(order=order, vehicle_type=vtype, fee=fee, note=note, driver=driver,
                                   proposed_by=user if getattr(user, 'pk', None) else None)
    previous = order.big_vehicle_driver if order.big_vehicle_driver_id else None
    same_driver = bool(driver and previous and previous.pk == driver.pk)
    order.big_vehicle_driver_state = (order.big_vehicle_driver_state if same_driver else 'pending') if driver else ''
    order.big_vehicle_state = 'proposed'
    order.big_vehicle_type = vtype
    order.big_vehicle_fee = fee
    order.big_vehicle_note = note
    order.big_vehicle_proposed_at = now()
    order.big_vehicle_driver = driver
    order.save(update_fields=['big_vehicle_state', 'big_vehicle_type', 'big_vehicle_fee',
                              'big_vehicle_note', 'big_vehicle_proposed_at', 'big_vehicle_driver',
                              'big_vehicle_driver_state', 'updated_at'])
    shop = store_name(order.vendor_id)
    if previous and (not driver or previous.pk != driver.pk):       # store ne doosri gari chun li
        _notify_big_vehicle_driver(previous, f'ℹ️ Order #{order.order_no}: not needed',
                                   f'{shop} chose another vehicle for this order.')
    if driver:
        _notify_big_vehicle_driver(
            driver, f'🚚 Order #{order.order_no}: you were picked',
            f'{shop} picked your vehicle for a delivery (fare Rs. {fee:,.0f}). '
            f'Open the app to accept or decline.')
    _notify(_customer_user(order),
            f'🚚 Order #{order.order_no}: big vehicle fare',
            f'{shop} says your order needs a {vtype}. Fare: Rs. {fee:,.0f}. '
            f'If you approve, your new total will be Rs. {big_vehicle_total_preview(order, fee):,.0f}. '
            f'Open the order to approve or cancel.' + _big_vehicle_deadline_text(),
            link=f'/shop/order/{order.id}/', kind='info', category='orders', priority='high')
    review_fee = _bv_setting('big_vehicle_review_fee', 0)
    if review_fee > 0 and fee >= review_fee:      # bahut zyada kiraya: admin dekh le
        _notify_admins(f'⚠️ Order #{order.order_no}: high big vehicle fare',
                       f'{shop} sent a fare of Rs. {fee:,.0f} ({vtype}) for this order. Please review it.',
                       f'/orders/sale/{order.id}/')


def withdraw_big_vehicle(order):
    """Store ne faisla badla: gari ka kiraya wapas lo, order rider se jayega. Sirf tab jab customer ne abhi manzoor na kiya ho."""
    state = getattr(order, 'big_vehicle_state', '')
    if state == 'approved':
        raise OrderActionError('The customer has already approved the big vehicle fare, so it cannot be switched back to a rider.')
    if state != 'proposed':
        raise OrderActionError('No big vehicle fare is pending for this order.')
    _close_big_vehicle_offer(order, 'superseded')
    released = order.big_vehicle_driver if order.big_vehicle_driver_id else None
    order.big_vehicle_state = ''
    order.big_vehicle_type = ''
    order.big_vehicle_fee = ZERO
    order.big_vehicle_note = ''
    order.big_vehicle_proposed_at = None
    order.big_vehicle_driver = None
    order.big_vehicle_driver_state = ''
    order.save(update_fields=['big_vehicle_state', 'big_vehicle_type', 'big_vehicle_fee',
                              'big_vehicle_note', 'big_vehicle_proposed_at', 'big_vehicle_driver',
                              'big_vehicle_driver_state', 'updated_at'])
    if released:
        _notify_big_vehicle_driver(released, f'ℹ️ Order #{order.order_no}: cancelled for you',
                                   'The store will send this order with a normal rider instead.')
    _notify(_customer_user(order), f'🏍️ Order #{order.order_no}: delivery by rider',
            f'{store_name(order.vendor_id)} will deliver your order with a normal rider, so no big vehicle fare is needed. '
            f'Your total stays the same.',
            link=f'/shop/order/{order.id}/', kind='info', category='orders')


def respond_big_vehicle(order, *, approve):
    """Customer kiraya manzoor ya radd karta hai. order select_for_update mein ho."""
    if getattr(order, 'big_vehicle_state', '') != 'proposed':
        raise OrderActionError('There is no fare waiting for approval right now.')
    prof = get_store_profile(order.vendor_id)
    from .vendor_access import notify_users
    _close_big_vehicle_offer(order, 'approved' if approve else 'declined')
    if approve:
        old_total = order_payable_total(order)    # kiraya lagne se pehle ka total
        order.big_vehicle_state = 'approved'
        order.delivery_fee = order.big_vehicle_fee
        order.pro_delivery_waived = ZERO          # Pro sirf aam delivery maaf karta hai, bari gari ka kiraya nahi
        new_total = order_payable_total(order)
        wallet_back = _settle_big_vehicle_wallet(order, new_total)
        drv = order.big_vehicle_driver if order.big_vehicle_driver_id else None
        if drv:                                   # list se chuni gari: number aur driver phone khud bhar do
            order.vehicle_no = drv.vehicle_no or order.vehicle_no
            order.big_vehicle_driver_phone = drv.phone or order.big_vehicle_driver_phone
        order.save(update_fields=['big_vehicle_state', 'delivery_fee', 'pro_delivery_waived',
                                  'wallet_paid', 'vehicle_no', 'big_vehicle_driver_phone', 'updated_at'])
        if drv:
            _notify_big_vehicle_driver(
                drv, f'✅ Order #{order.order_no}: job confirmed',
                f'The customer approved the fare of Rs. {order.big_vehicle_fee:,.0f}. '
                f'Open the app for pickup and delivery details.')
        pay_note = _big_vehicle_payment_note(order, old_total, new_total, wallet_back)
        msg = (f'The customer approved the big vehicle fare of Rs. {order.big_vehicle_fee:,.0f}. '
               f'New total Rs. {new_total:,.0f}. {pay_note} You can now mark the order Ready.')
        title = f'✅ Order #{order.order_no}: fare approved'
    else:
        order.big_vehicle_state = 'declined'
        order.save(update_fields=['big_vehicle_state', 'updated_at'])
        if order.big_vehicle_driver_id:
            _notify_big_vehicle_driver(order.big_vehicle_driver, f'❌ Order #{order.order_no}: cancelled',
                                       'The customer did not approve the fare, so this job is cancelled.')
        apply_vendor_action(order, 'reject', user=None, reason_code='other',
                            reason_note='The customer did not approve the big vehicle fare.')
        msg = 'The customer did not approve the big vehicle fare, so the order was cancelled.'
        title = f'❌ Order #{order.order_no}: fare declined'
    if prof:
        for target in notify_users(prof):
            _notify(target, title, msg, link='/shop/vendor/orders/', kind='sale', category='orders', priority='high')


def _settle_big_vehicle_wallet(order, new_total):
    """
    Naya total wallet se pehle di hui raqam se kam ho jaye (store ne purani delivery fee se kam kiraya likha)
    to farq customer ke wallet mein wapas. order.wallet_paid ghat kar naye total ke barabar ho jata hai,
    taake baad mein cancel par poora sahi refund ho. Wapas: wapas gayi raqam (ya 0). order.save() caller karta hai.
    """
    from ..models import WalletTransaction
    paid = Decimal(order.wallet_paid or 0)
    if paid <= new_total or not order.customer_id:
        return ZERO
    if not WalletTransaction.objects.filter(order=order, kind='spend').exists():
        return ZERO
    back = paid - new_total
    obj, created = WalletTransaction.objects.get_or_create(
        order=order, kind='adjust',
        defaults={'customer_id': order.customer_id, 'amount': back,
                  'note': f'Fare difference returned (lower big vehicle fare): order #{order.order_no}'})
    if not created:
        return ZERO
    order.wallet_paid = new_total
    return back


def _big_vehicle_payment_note(order, old_total, new_total, wallet_back):
    """Manzoori ke baad payment ka seedha jumla (store ko dikhane ke liye); online-paid order mein farq admin ko bhi batata hai."""
    parts = []
    if wallet_back > 0:
        parts.append(f'Rs. {wallet_back:,.0f} went back to the customer wallet.')
    if (order.payment_method or 'cod') == 'cod':
        parts.append(f'Cash on delivery: Rs. {order_cash_due(order):,.0f}.')
    else:
        extra = new_total - old_total
        if extra > 0:
            parts.append(f'The order was paid online: collect the fare difference of Rs. {extra:,.0f} from the customer separately.')
            _notify_admins(f'ℹ️ Order #{order.order_no}: fare difference to collect',
                           f'The order was paid online. After the big vehicle fare was approved, the total went from '
                           f'Rs. {old_total:,.0f} to Rs. {new_total:,.0f}. Collect the difference of Rs. {extra:,.0f} '
                           f'from the customer separately.', f'/orders/sale/{order.id}/')
        elif extra < 0:
            parts.append(f'The order was paid online: the fare is Rs. {-extra:,.0f} lower than before, so return the difference to the customer.')
            _notify_admins(f'ℹ️ Order #{order.order_no}: fare difference to refund',
                           f'The order was paid online. After the big vehicle fare was approved, the total went from '
                           f'Rs. {old_total:,.0f} to Rs. {new_total:,.0f}. Return the difference of Rs. {-extra:,.0f} '
                           f'to the customer.', f'/orders/sale/{order.id}/')
    return ' '.join(parts)


def expire_big_vehicle_proposals(order_id=None):
    """
    Jis kiraye par customer ne waqt par jawab nahi diya, uska order cancel karo (customer aur store
    dono ko notification, online payment mein admin ko refund yaad dilana). Wapas: kitne order cancel hue.
    """
    from django.db import transaction
    from ..models import SaleOrder

    minutes = big_vehicle_timeout_minutes()
    if not minutes:
        return 0
    cutoff = now() - timedelta(minutes=minutes)
    due = SaleOrder.objects.filter(big_vehicle_state='proposed', big_vehicle_proposed_at__lte=cutoff,
                                   status__in=('confirmed', 'processing'))
    if order_id is not None:
        due = due.filter(pk=order_id)
    expired = 0
    for oid in list(due.values_list('id', flat=True)[:200]):
        try:
            with transaction.atomic():
                order = SaleOrder.objects.select_for_update().get(pk=oid)
                deadline = big_vehicle_deadline(order)
                if (order.status not in ('confirmed', 'processing') or not deadline or now() < deadline):
                    continue            # is dauran customer ne jawab de diya ya kiraya badal gaya
                _close_big_vehicle_offer(order, 'expired')
                order.big_vehicle_state = 'declined'    # cancel wala rasta wahi hai jo "radd" ka hai
                order.save(update_fields=['big_vehicle_state', 'updated_at'])
                if order.big_vehicle_driver_id:
                    _notify_big_vehicle_driver(order.big_vehicle_driver, f'⏰ Order #{order.order_no}: expired',
                                               'The customer did not respond in time, so this job is cancelled.')
                apply_vendor_action(order, 'reject', user=None, reason_code='other',
                                    reason_note='The customer did not respond to the big vehicle fare in time.')
                prof = get_store_profile(order.vendor_id)
                if prof:
                    from .vendor_access import notify_users
                    for target in notify_users(prof):
                        _notify(target, f'⏰ Order #{order.order_no}: fare expired',
                                'The customer did not respond to the big vehicle fare in time, '
                                'so the order was cancelled.',
                                link='/shop/vendor/orders/', kind='sale', category='orders', priority='high')
                expired += 1
        except Exception as exc:
            logger.error("Big vehicle expire failed for %s: %s", oid, exc)
    return expired


def _notify_store_users(order, title, message):
    prof = get_store_profile(order.vendor_id)
    if not prof:
        return
    from .vendor_access import notify_users
    for target in notify_users(prof):
        _notify(target, title, message, link='/shop/vendor/orders/', kind='sale', category='orders', priority='high')


def _driver_job_check(order, driver):
    if (not order.big_vehicle_driver_id or order.big_vehicle_driver_id != driver.pk
            or order.big_vehicle_state not in ('proposed', 'approved')
            or order.status not in ('confirmed', 'processing', 'ready')):
        raise OrderActionError('This job is not assigned to you anymore.')


def driver_respond_big_vehicle(order, driver, *, accept):
    """Gari ka driver store ki chuni hui job accept ya decline karta hai. order select_for_update mein ho."""
    _driver_job_check(order, driver)
    if order.big_vehicle_driver_state == 'accepted':
        if accept:
            return
        if order.status == 'ready':
            raise OrderActionError('The order is already ready for pickup. Call the store if you cannot take it.')
    shop = store_name(order.vendor_id)
    if accept:
        order.big_vehicle_driver_state = 'accepted'
        order.save(update_fields=['big_vehicle_driver_state', 'updated_at'])
        _notify_store_users(order, f'✅ Order #{order.order_no}: driver accepted',
                            f'{driver.name} accepted the big vehicle job'
                            + (f' ({driver.vehicle_no})' if driver.vehicle_no else '') + '.')
        return
    # Decline: gari hat jati hai
    if order.big_vehicle_state == 'proposed':
        _close_big_vehicle_offer(order, 'superseded')
        order.big_vehicle_state = ''
        order.big_vehicle_type = ''
        order.big_vehicle_fee = ZERO
        order.big_vehicle_note = ''
        order.big_vehicle_proposed_at = None
        order.big_vehicle_driver = None
        order.big_vehicle_driver_state = ''
        order.save(update_fields=['big_vehicle_state', 'big_vehicle_type', 'big_vehicle_fee', 'big_vehicle_note',
                                  'big_vehicle_proposed_at', 'big_vehicle_driver', 'big_vehicle_driver_state', 'updated_at'])
        _notify(_customer_user(order), f'ℹ️ Order #{order.order_no}: fare withdrawn',
                f'The vehicle for your order is not available. {shop} will send you an updated fare. Your total has not changed.',
                link=f'/shop/order/{order.id}/', kind='info', category='orders')
    else:                                           # kiraya manzoor ho chuka: kiraya wahi, gari badalni hai
        order.big_vehicle_driver = None
        order.big_vehicle_driver_state = ''
        order.vehicle_no = None
        order.big_vehicle_driver_phone = ''
        order.save(update_fields=['big_vehicle_driver', 'big_vehicle_driver_state', 'vehicle_no',
                                  'big_vehicle_driver_phone', 'updated_at'])
    _notify_store_users(order, f'❌ Order #{order.order_no}: driver declined',
                        f'{driver.name} declined the big vehicle job. Please pick another vehicle'
                        + (' and send the fare again.' if order.big_vehicle_state == '' else ', or enter one manually.'))


def assign_big_vehicle_driver(order, driver_id):
    """Kiraya manzoor hone ke baad store dusri gari chunta hai (ya khali = manual). Driver accept kar chuka ho to nahi."""
    if getattr(order, 'big_vehicle_state', '') != 'approved':
        raise OrderActionError('You can change the vehicle after the customer approves the fare.')
    if order.status not in ('confirmed', 'processing', 'ready'):
        raise OrderActionError('This order can no longer be changed.')
    if order.big_vehicle_driver_id and order.big_vehicle_driver_state == 'accepted':
        raise OrderActionError('The driver has already accepted this job.')
    new = _pick_big_vehicle_driver(driver_id, order)
    old = order.big_vehicle_driver if order.big_vehicle_driver_id else None
    if new and old and new.pk == old.pk:
        return
    order.big_vehicle_driver = new
    order.big_vehicle_driver_state = 'pending' if new else ''
    if new:
        order.vehicle_no = new.vehicle_no or None
        order.big_vehicle_driver_phone = new.phone or ''
        if new.vehicle:
            order.big_vehicle_type = new.vehicle[:60]
    order.save(update_fields=['big_vehicle_driver', 'big_vehicle_driver_state', 'vehicle_no',
                              'big_vehicle_driver_phone', 'big_vehicle_type', 'updated_at'])
    shop = store_name(order.vendor_id)
    if old:
        _notify_big_vehicle_driver(old, f'ℹ️ Order #{order.order_no}: not needed', f'{shop} chose another vehicle.')
    if new:
        _notify_big_vehicle_driver(new, f'🚚 Order #{order.order_no}: you were picked',
                                   f'{shop} picked your vehicle (fare Rs. {order.big_vehicle_fee:,.0f}, approved by the customer). '
                                   f'Open the app to accept or decline.')


def driver_deliver_big_vehicle(order, driver):
    """Driver customer ko order de kar \"Delivered\" dabata hai. order select_for_update mein ho."""
    _driver_job_check(order, driver)
    if order.big_vehicle_state != 'approved' or order.big_vehicle_driver_state != 'accepted':
        raise OrderActionError('Accept the job first. The customer must also approve the fare.')
    if order.status != 'ready':
        raise OrderActionError('The store has not marked this order Ready yet.')
    apply_vendor_action(order, 'delivered', user=driver.user)
    _notify_store_users(order, f'🎉 Order #{order.order_no}: delivered',
                        f'{driver.name} marked the big vehicle order as delivered.')


def update_big_vehicle_details(order, *, vehicle_no, driver_phone):
    """Manzoor hone ke baad store gari ka number aur driver ka phone likhta hai (customer ko order page par dikhta hai)."""
    if getattr(order, 'big_vehicle_state', '') != 'approved':
        raise OrderActionError('Enter the vehicle details after the fare is approved.')
    phone = ''.join(ch for ch in (driver_phone or '') if ch.isdigit() or ch == '+')[:20]
    new_no = ' '.join((vehicle_no or '').split())[:30] or None
    changed = (new_no != order.vehicle_no) or (phone != order.big_vehicle_driver_phone)
    order.vehicle_no = new_no
    order.big_vehicle_driver_phone = phone
    order.save(update_fields=['vehicle_no', 'big_vehicle_driver_phone', 'updated_at'])
    if changed and (new_no or phone):         # customer ko batao (sirf jab detail asal mein badli ho)
        bits = []
        if new_no:
            bits.append(f'the vehicle number {new_no}')
        if phone:
            bits.append(f'the driver phone {phone}')
        _notify(_customer_user(order), f'🚚 Order #{order.order_no}: vehicle details',
                f'{store_name(order.vendor_id)} shared {" and ".join(bits)}.',
                link=f'/shop/order/{order.id}/', kind='info', category='orders', priority='normal')
