"""Store handover code: store order dete waqt rider ko 4 digit code batata hai, rider pickup par wahi code deta hai.

Code order se HMAC (SECRET_KEY) ke zariye banta hai - database mein kuch save nahi hota, migration nahi chahiye.
Galat code ki koshishon par rider thodi der ke liye is order par lock ho jata hai.
"""
import hashlib
import hmac

from django.conf import settings
from django.core.cache import cache

MAX_WRONG = 5            # itni galat koshishon ke baad lock
LOCK_SECONDS = 10 * 60


def code_for(order):
    """Order ka 4 digit pickup code (string, jaise '0482'). Delivery OTP se alag hai."""
    msg = f'pickup-code:{order.pk}:{order.order_no}'.encode()
    digest = hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).digest()
    return f'{int.from_bytes(digest[:4], "big") % 10000:04d}'


def _key(order_id):
    return f'pickup-code-wrong:{order_id}'


def is_locked(order_id):
    return (cache.get(_key(order_id)) or 0) >= MAX_WRONG


def check(order, entered):
    """-> (ok, message). Sahi code par counter saaf; galat par counter barhta hai."""
    if is_locked(order.pk):
        return False, 'Too many wrong codes. Please wait a few minutes or ask the store to hand over the order.'
    entered = ''.join(ch for ch in (entered or '') if ch.isdigit())
    if entered and hmac.compare_digest(entered, code_for(order)):
        cache.delete(_key(order.pk))
        return True, ''
    n = (cache.get(_key(order.pk)) or 0) + 1
    cache.set(_key(order.pk), n, LOCK_SECONDS)
    if not entered:
        return False, 'Ask the store for the 4-digit pickup code and enter it.'
    left = MAX_WRONG - n
    return False, 'Wrong pickup code.' + (f' {left} tries left.' if left > 0 else ' Locked for a few minutes.')
