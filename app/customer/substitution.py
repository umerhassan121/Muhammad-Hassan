"""Mart (dark store) substitution preference: agar koi item stock mein na ho to kya karein.

Customer cart page par ek choice karta hai (session mein 'sub_pref'), aur wo order ke notes mein
likh di jati hai taake store / rider ko nazar aaye. Sirf dark store (Mart) ke cart par lagu hota hai.
Koi bhi galti ho to order nahi rukta: bas line nahi judti.
"""
import logging

logger = logging.getLogger(__name__)

SESSION_KEY = 'sub_pref'
DEFAULT = 'best'
CHOICES = (
    ('best', 'Replace with the best match', 'Store picks the closest item.'),
    ('call', 'Call me first', 'We will call before changing anything.'),
    ('remove', 'Remove the item', 'Skip it and take its amount off the bill.'),
)
_LABELS = {k: label for k, label, _ in CHOICES}


def clean(value):
    value = (value or '').strip().lower()
    return value if value in _LABELS else DEFAULT


def current(session):
    return clean(session.get(SESSION_KEY))


def cart_is_mart(cart):
    """True = cart ka store dark store (Mart) hai."""
    try:
        from . import store_orders
        from ..models import VendorProfile
        vid = store_orders.cart_store_id(cart or {})
        return bool(vid) and VendorProfile.objects.filter(vendor_id=vid, is_dark_store=True).exists()
    except Exception:
        logger.exception('substitution.cart_is_mart')
        return False


def note_line(session, cart):
    """Order notes ke liye ek line ('' agar Mart cart nahi)."""
    try:
        if not cart_is_mart(cart):
            return ''
        return f"\nIf out of stock: {_LABELS[current(session)]}"
    except Exception:
        logger.exception('substitution.note_line')
        return ''
