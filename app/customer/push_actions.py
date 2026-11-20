"""Notification ke buttons se seedha order accept / reject (app khole baghair).

Kaise chalta hai:
  * Naya order aane par push ke saath har button ka ek *signed token* jata hai (user + order + action, 15 minute valid).
  * Service worker button dabne par POST /shop/push/action/ {token} bhejta hai (session/CSRF ki zaroorat nahi:
    token server ke SECRET_KEY se sign hai, koi bana nahi sakta).
  * Server wahi checks lagata hai jo web page par lagte hain (approved vendor, flag on, apna hi order, status sahi).
Vendor : Accept / Reject (reject ki wajah "store busy" likhi jati hai)
Rider  : Accept / Decline (offer)
Vendor ko order ka jawab na milne par 3 dafa yaad-dahani (reminder) push bhi jati hai.
"""
import json
import logging
import threading
import time

from django.contrib.auth.models import User
from .vendor_access import get_vendor_profile
from django.core import signing
from django.db import connection, transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ..shop_flags import shop_flag

logger = logging.getLogger(__name__)

SALT = 'pwa-push-action'
MAX_AGE = 15 * 60                 # token itni der valid
REMINDER_DELAY = 45               # second
REMINDER_COUNT = 3


def make_token(user, kind, order_id, action):
    return signing.dumps({'u': user.pk, 'k': kind, 'o': int(order_id), 'a': action}, salt=SALT, compress=True)


def vendor_buttons(user, order):
    return [
        {'action': 'accept', 'title': 'Accept', 'oid': order.pk, 'token': make_token(user, 'vendor', order.pk, 'accept')},
        {'action': 'reject', 'title': 'Reject', 'oid': order.pk, 'token': make_token(user, 'vendor', order.pk, 'reject')},
    ]


def rider_buttons(user, order):
    return [
        {'action': 'accept', 'title': 'Accept', 'oid': order.pk, 'token': make_token(user, 'rider', order.pk, 'accept')},
        {'action': 'decline', 'title': 'Decline', 'oid': order.pk, 'token': make_token(user, 'rider', order.pk, 'decline')},
    ]


def _fail(msg, status=200):
    return JsonResponse({'ok': False, 'message': msg}, status=status)


def _ok(msg):
    return JsonResponse({'ok': True, 'message': msg})


# ---------------- vendor ----------------

def _vendor_action(user, order_id, action):
    from ..models import SaleOrder
    from . import store_orders
    if action not in ('accept', 'reject'):
        return _fail('Invalid action.')
    from .vendor_access import accessible_profiles
    profiles = accessible_profiles(user)
    if not profiles:
        return _fail('Your account is not approved.')
    if not shop_flag('vendor_can_manage_orders'):
        return _fail('Managing orders is turned off right now.')
    try:
        with transaction.atomic():
            order = SaleOrder.objects.select_for_update().filter(
                pk=order_id, vendor_id__in=[p.vendor_id for p in profiles if p.is_approved]).first()
            if order is None:
                return _fail('Order not found.')
            store_orders.apply_vendor_action(
                order, action, user=user,
                reason_code='store_busy' if action == 'reject' else '')
    except store_orders.OrderActionError as exc:
        return _fail(str(exc))
    if action == 'accept':
        return _ok('Order #%s qubool kar liya.' % order.order_no)
    return _ok('Order #%s reject kar diya.' % order.order_no)


# ---------------- rider ----------------

def _rider_action(user, order_id, action):
    from ..models import DeliveryInfo, SaleOrder
    from . import dispatch, store_orders
    from .views_rider_portal import ACTIVE_STATUSES, MAX_ACTIVE_ORDERS, _assign
    if action not in ('accept', 'decline'):
        return _fail('Invalid action.')
    rider = getattr(user, 'rider_profile', None)
    if rider is None or not rider.is_active:
        return _fail('Your rider account is not active.')

    if action == 'decline':
        order = SaleOrder.objects.filter(pk=order_id, status='ready').first()
        if order and dispatch.can_take(order, rider, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES):
            dispatch.decline(order, rider)
        return _ok('Order declined.')

    if not shop_flag('rider_can_accept_orders'):
        return _fail('Accepting orders is turned off right now.')
    if not rider.is_online:
        return _fail('Please go Online in the app first.')
    if DeliveryInfo.objects.filter(rider=rider, status__in=ACTIVE_STATUSES).count() >= MAX_ACTIVE_ORDERS:
        return _fail('You already have %d orders.' % MAX_ACTIVE_ORDERS)
    try:
        with transaction.atomic():
            order = (SaleOrder.objects.select_for_update().filter(pk=order_id, status='ready')
                     .exclude(big_vehicle_state__in=['proposed', 'approved']).first())
            if not order:
                raise store_orders.OrderActionError('This order is no longer available.')
            if not dispatch.can_take(order, rider, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES):
                raise store_orders.OrderActionError('This order is currently being offered to another rider.')
            di, _ = DeliveryInfo.objects.select_for_update().get_or_create(sale_order=order)
            if di.rider_id and di.status != 'cancelled':
                raise store_orders.OrderActionError('This order was taken by another rider.')
            _assign(order, di, rider, user)
    except store_orders.OrderActionError as exc:
        return _fail(str(exc))
    return _ok('Order #%s is yours. Pick it up from %s.' % (order.order_no, store_orders.store_name(order.vendor_id)))


def _localized(resp, lang):
    """Rider ki language Urdu ho to jawab ka message Urdu mein (APK ka receiver cookie se `lang` bhejta hai)."""
    if lang != 'ur':
        return resp
    try:
        from ..i18n.server_t import translate
        data = json.loads(resp.content.decode('utf-8'))
        data['message'] = translate(data.get('message', ''), 'ur')
        return JsonResponse(data, status=resp.status_code)
    except Exception as exc:            # tarjume mein masla ho to English jawab hi jaye
        logger.error('push_action translate error: %s', exc)
        return resp


@csrf_exempt
@require_POST
def push_action(request):
    """Notification button -> {ok, message}."""
    lang = 'en'
    try:
        body = json.loads(request.body or b'{}')
        lang = 'ur' if str(body.get('lang') or '') == 'ur' else 'en'
        token = str(body.get('token') or '')
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.SignatureExpired:
        return _localized(_fail('This button has expired. Please open the app.', 400), lang)
    except (signing.BadSignature, ValueError, AttributeError):
        return _fail('Galat request.', 400)
    user = User.objects.filter(pk=data.get('u'), is_active=True).first()
    if user is None:
        return _localized(_fail('User not found.', 400), lang)
    try:
        if data.get('k') == 'vendor':
            return _vendor_action(user, data.get('o'), data.get('a'))
        if data.get('k') == 'rider':
            return _localized(_rider_action(user, data.get('o'), data.get('a')), lang)
    except Exception as exc:       # button se kabhi 500 na jaye
        logger.error('push_action error: %s', exc)
        return _localized(_fail('Something went wrong. Please open the app.'), lang)
    return _fail('Galat request.', 400)


# ---------------- vendor reminders ----------------

def _remind_worker(order_id, user_id, delays):
    from ..models import SaleOrder
    from .. import push_service
    try:
        for n, delay in enumerate(delays, 1):
            time.sleep(delay)
            order = SaleOrder.objects.filter(pk=order_id).first()
            user = User.objects.filter(pk=user_id, is_active=True).first()
            if not order or not user or order.status != 'pending':
                return                                    # jawab de diya (ya expire) - bas
            push_service.send_push(
                user, '⏰ Please respond to order #%s' % order.order_no,
                'The customer is waiting (%d/%d).' % (n, len(delays)),
                '/shop/vendor/orders/', 'vendor', vendor_buttons(user, order))
    except Exception as exc:
        logger.error('reminder error: %s', exc)
    finally:
        try:
            connection.close()
        except Exception:
            pass


def schedule_vendor_reminders(order, user):
    """Order pending rahe to 45 second ke baad dobara push (max 3). Ek process ke andar thread; kabhi exception nahi."""
    try:
        if not (order and user):
            return
        threading.Thread(target=_remind_worker, args=(order.pk, user.pk, [REMINDER_DELAY] * REMINDER_COUNT),
                         daemon=True).start()
    except Exception as exc:
        logger.error('schedule reminders error: %s', exc)


# ---------------- rider offers ----------------

def push_offer_to_rider(order, rider_id):
    """Rider ko naye offer ki push (Accept/Decline buttons ke saath). Kabhi exception nahi."""
    try:
        from ..models import RiderProfile
        from .. import push_service
        from . import store_orders
        rider = RiderProfile.objects.filter(pk=rider_id, is_active=True, is_online=True, approval_status='approved', rider_kind='bike').select_related('user').first()
        if not rider or not rider.user_id:
            return
        push_service.send_push_after_commit(
            rider.user, '🆕 New order #%s' % order.order_no,
            'Pick up the order from %s.' % store_orders.store_name(order.vendor_id),
            '/shop/rider/', 'rider', rider_buttons(rider.user, order))
    except Exception as exc:
        logger.error('push_offer_to_rider error: %s', exc)


def push_next_offer(order, declined_rider_id):
    """Rider ne decline kiya: ranking mein agle rider ko offer ki push."""
    try:
        from ..models import DispatchAttempt
        att = DispatchAttempt.objects.filter(sale_order=order).first()
        if not att or not att.ranking or declined_rider_id not in att.ranking:
            return
        idx = att.ranking.index(declined_rider_id)
        for rid in att.ranking[idx + 1:]:
            if rid not in att.declined:
                push_offer_to_rider(order, rid)
                return
    except Exception as exc:
        logger.error('push_next_offer error: %s', exc)
