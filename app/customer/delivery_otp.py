"""Delivery OTP: customer ko 4 digit code dikhta hai, rider ko deliver karte waqt wahi code dena hota hai.

Code order se HMAC (SECRET_KEY) ke zariye banta hai - database mein kuch save nahi hota, migration nahi chahiye.
Galat code ki koshishon par rider thodi der ke liye lock ho jata hai (4 digit ko andaze se tornay se bachane ke liye).
"""
import hashlib
import hmac

from django.conf import settings
from django.core.cache import cache

MAX_WRONG = 5            # itni galat koshishon ke baad lock
LOCK_SECONDS = 30 * 60


def code_for(order):
    """Order ka 4 digit code (string, jaise '0482')."""
    msg = f'delivery-otp:{order.pk}:{order.order_no}'.encode()
    digest = hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).digest()
    return f'{int.from_bytes(digest[:4], "big") % 10000:04d}'


def _key(order_id):
    return f'delivery-otp-wrong:{order_id}'


def is_locked(order_id):
    return (cache.get(_key(order_id)) or 0) >= MAX_WRONG


def check(order, entered):
    """-> (ok, message). Sahi code par counter saaf; galat par counter barhta hai."""
    if is_locked(order.pk):
        return False, 'Too many wrong codes. Please contact the admin to complete this delivery.'
    entered = ''.join(ch for ch in (entered or '') if ch.isdigit())
    if entered and hmac.compare_digest(entered, code_for(order)):
        cache.delete(_key(order.pk))
        return True, ''
    n = (cache.get(_key(order.pk)) or 0) + 1
    cache.set(_key(order.pk), n, LOCK_SECONDS)
    if not entered:
        return False, 'Ask the customer for the 4-digit delivery code and enter it.'
    left = MAX_WRONG - n
    return False, 'Wrong delivery code.' + (f' {left} tries left.' if left > 0 else ' Locked - contact the admin.')
