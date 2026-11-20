"""Failed delivery / return flow (Talabat jaisa).

1. Rider "Can't deliver" dabata hai (wajah + note)  -> DeliveryFailure 'waiting'. Customer ko khabar jati hai;
   customer order page par "I'm ready" dabaye to rider ko batata hai ke deliver kar sakta hai.
2. Rider kam az kam `rider_failed_wait_minutes` (default 10) intezar kare (customer ne mana kiya ho to foran),
   phir "Return to store" -> DeliveryInfo 'returned', rider ko (percent) fee, store aur admin ko khabar.
3. Admin "Failed deliveries" page par Re-dispatch (naya rider) ya Cancel order (wallet ka paisa wapas, online
   payment par refund yaad-dahani) chunta hai.
Order ki status 'ready' hi rehti hai jab tak admin faisla na kare.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

REASONS = [
    ('unreachable', 'Customer is not answering'),
    ('wrong_address', 'Wrong or unfindable address'),
    ('refused', 'Customer refused the order'),
    ('other', 'Other'),
]
REASON_LABELS = dict(REASONS)
NO_WAIT_REASONS = ('refused',)


class ReturnError(Exception):
    """Rider/admin ko seedha dikhai ja sakne wali ghalti."""


# ---------------- pure ----------------
def wait_seconds_left(reported_at, wait_minutes, reason, now):
    """Return se pehle kitne second baqi (0 = ab return kar sakta hai)."""
    if reason in NO_WAIT_REASONS or wait_minutes <= 0:
        return 0
    left = (reported_at - now).total_seconds() + wait_minutes * 60
    return max(int(left) + (1 if left % 1 else 0), 0)


def fee_for(per_delivery_fee, percent):
    pct = min(max(Decimal(percent or 0), Decimal('0')), Decimal('100'))
    return (Decimal(per_delivery_fee or 0) * pct / Decimal('100')).quantize(Decimal('0.01'), ROUND_HALF_UP)


# ---------------- settings ----------------
def wait_minutes():
    from .offers import setting_decimal
    return int(setting_decimal('rider_failed_wait_minutes', '10'))


def fee_percent():
    from .offers import setting_decimal
    return setting_decimal('rider_failed_fee_percent', '100')


def seconds_left(failure, now=None):
    return wait_seconds_left(failure.reported_at, wait_minutes(), failure.reason, now or timezone.now())


# ---------------- notifications ----------------
def _admins():
    from django.contrib.auth.models import User
    return User.objects.filter(is_superuser=True, is_active=True)


def _safe(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('delivery return notify failed')


# ---------------- rider side ----------------
def open_failure(di):
    return di.failures.filter(status='waiting').first()


def report(order, di, rider, reason, note=''):
    from ..models import DeliveryFailure
    from . import store_orders
    if reason not in REASON_LABELS:
        raise ReturnError('Choose why you cannot deliver.')
    note = (note or '').strip()[:200]
    if reason == 'other' and not note:
        raise ReturnError('Please write the reason.')
    if di.status not in ('picked_up', 'in_transit'):
        raise ReturnError('You can report a problem only after picking up the order.')
    if open_failure(di):
        raise ReturnError('A problem is already reported for this order.')
    f = DeliveryFailure.objects.create(delivery=di, sale_order=order, rider=rider, reason=reason, note=note)
    link = f'/shop/order/{order.id}/'
    if reason == 'refused':
        msg = f'Your rider reports that the order #{order.order_no} was refused.'
    else:
        msg = (f'Rider {rider.name} could not deliver order #{order.order_no}: {REASON_LABELS[reason]}. '
               f'Please contact the rider ({rider.phone}) and tap "I am ready" on the order page.')
    _safe(store_orders._notify, store_orders._customer_user(order), '⚠️ Delivery problem', msg, link, 'warning')
    for a in _admins():
        _safe(store_orders._notify, a, f'⚠️ Order #{order.order_no}: delivery problem',
              f'{rider.name}: {REASON_LABELS[reason]}' + (f' - {note}' if note else ''),
              '/shop/rider/manage/returns/', 'warning', category='orders')
    return f


def mark_returned(order, di, rider):
    """Rider order store ko wapas le gaya. Intezar ka waqt poora na hua ho to ReturnError."""
    from . import store_orders
    f = open_failure(di)
    if not f:
        raise ReturnError('Report the delivery problem first.')
    if f.customer_ready:
        raise ReturnError('The customer says they are ready. Please deliver the order.')
    left = seconds_left(f)
    if left > 0:
        raise ReturnError(f'Please wait {-(-left // 60)} more minute(s) before returning the order.')
    f.status = 'returned'
    f.returned_at = timezone.now()
    f.rider_fee = fee_for(rider.per_delivery_fee, fee_percent())
    f.save(update_fields=['status', 'returned_at', 'rider_fee'])
    di.status = 'returned'
    di.save(update_fields=['status', 'updated_at'])
    from .views_rider_portal import _track, _vendor_user
    _safe(_track, order, 'delivery_failed', 'Delivery failed',
          f'{REASON_LABELS[f.reason]}. Rider {rider.name} returned the order to the store.', rider.user, rider)
    _safe(store_orders._notify, _safe(_vendor_user, order), f'↩️ Order #{order.order_no} returned',
          f'Rider {rider.name} brought the order back ({REASON_LABELS[f.reason]}).',
          '/shop/vendor/orders/?tab=active', 'warning', category='riders')
    _safe(store_orders._notify, store_orders._customer_user(order), f'Order #{order.order_no} returned to the store',
          'We could not deliver your order. Our team will contact you.', f'/shop/order/{order.id}/', 'warning')
    for a in _admins():
        _safe(store_orders._notify, a, f'↩️ Order #{order.order_no} is back at the store',
              'Decide: send it again with another rider, or cancel it.', '/shop/rider/manage/returns/', 'warning',
              category='orders')
    return f


def close_open(di, resolution):
    """Rider ne order phir bhi deliver kar diya: khuli failure band."""
    f = open_failure(di)
    if f:
        f.status, f.resolution, f.closed_at = 'closed', resolution, timezone.now()
        f.save(update_fields=['status', 'resolution', 'closed_at'])


# ---------------- customer side ----------------
def customer_ready(order, customer):
    from ..models import DeliveryFailure
    from . import store_orders
    with transaction.atomic():
        f = (DeliveryFailure.objects.select_for_update()
             .filter(sale_order=order, status='waiting').select_related('rider', 'rider__user').first())
        if not f:
            raise ReturnError('There is no delivery problem to update.')
        f.customer_ready = True
        f.save(update_fields=['customer_ready'])
    _safe(store_orders._notify, f.rider.user, f'🙋 Order #{order.order_no}: customer is ready',
          'The customer says they are available now. Please deliver the order.', '/shop/rider/', 'success')
    return f


# ---------------- admin side ----------------
def _admin_close(request_id, resolution, user):
    from ..models import DeliveryFailure
    f = (DeliveryFailure.objects.select_for_update()
         .select_related('delivery', 'sale_order', 'rider').get(pk=request_id))
    if f.status != 'returned':
        raise ReturnError('This order is not waiting for a decision.')
    f.status, f.resolution, f.closed_at, f.closed_by = 'closed', resolution, timezone.now(), user
    f.save(update_fields=['status', 'resolution', 'closed_at', 'closed_by'])
    return f


def redispatch(failure_id, user):
    """Order phir se offers mein (rider khali, status pending); DispatchAttempt saaf taake nayi ranking bane."""
    from ..models import DispatchAttempt
    with transaction.atomic():
        f = _admin_close(failure_id, 'redispatched', user)
        di = f.delivery
        di.rider = None
        di.rider_name = di.rider_contact = di.rider_vehicle = None
        di.status = 'pending'
        di.picked_up_at = None
        di.peak_bonus = 0
        di.arrived_store_at = di.arrived_customer_at = None
        di.save()
        DispatchAttempt.objects.filter(sale_order=f.sale_order).delete()
    return f


def cancel_order(failure_id, user, reason=''):
    """Order cancel: SaleOrder 'cancelled' (signal wallet ka paisa wapas karta hai); online payment par refund yaad-dahani."""
    from . import store_orders
    reason = (reason or '').strip()[:200] or 'Delivery failed: ' + 'could not reach the customer'
    with transaction.atomic():
        f = _admin_close(failure_id, 'cancelled', user)
        order = f.sale_order
        order.status = 'cancelled'
        order.reject_reason = reason
        order.save()
        f.delivery.status = 'cancelled'
        f.delivery.save(update_fields=['status', 'updated_at'])
    shop = store_orders.store_name(order.vendor_id)
    _safe(store_orders._notify_event, store_orders._customer_user(order), 'order_cancelled_customer',
          {'order_no': order.order_no, 'store': shop, 'reason': reason, 'refund_note': store_orders.refund_note(order)},
          f'/shop/order/{order.id}/')
    if (order.payment_method or 'cod') != 'cod':
        _safe(store_orders._notify_admin_event, 'refund_due',
              {'order_no': order.order_no, 'store': shop, 'reason': reason, 'method': order.payment_method,
               'total': f'Rs. {store_orders.order_payable_total(order):,.0f}'},
              link=f'/orders/sale/{order.id}/')
    return f
