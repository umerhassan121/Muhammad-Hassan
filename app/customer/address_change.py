"""Pending order ka address badalne par delivery fee ka hisab + store ko khabar.

Fee tab hi badalti hai jab admin switch `shop_distance_fee_enabled` ON ho aur naye / purane address mein
DeliveryArea (extra_fee wala) ka naam aaye. Fee = purani fee - purane area ka extra + naye area ka extra.
Doori wala hissa nahi badalta (naya pin nahi hota). Pro se maaf / free delivery wale order ki fee nahi chhoori jati.
"""
import logging
from decimal import Decimal

ZERO = Decimal('0')
logger = logging.getLogger(__name__)
NOTE_TAG = 'ADDRESS CHANGED'


def area_extra_for_text(text, areas):
    """areas: [(naam, extra_fee)]. Address text mein jis area ka naam aaye uska sab se bara extra. (extra, naam)"""
    low = (text or '').lower()
    best = (ZERO, '')
    for name, extra in areas:
        extra = Decimal(extra or 0)
        if name and name.lower() in low and extra > best[0]:
            best = (extra, name)
    return best


def new_delivery_fee(old_fee, old_extra, new_extra, waived=ZERO):
    """Pure hisab. Maaf / free delivery ho to wahi fee; warna delta lagao (0 se neeche nahi)."""
    old_fee = Decimal(old_fee or 0)
    if old_fee <= 0 or Decimal(waived or 0) > 0:
        return old_fee
    return max(old_fee - Decimal(old_extra or 0) + Decimal(new_extra or 0), ZERO)


def _areas():
    from ..models import DeliveryArea
    return [(a.name, a.extra_fee) for a in DeliveryArea.objects.filter(is_active=True, extra_fee__gt=0)]


def fee_for_change(order, old_addr, new_addr):
    """(nayi fee, badli?)"""
    from ..module_config.shop_flags import shop_flag
    old_fee = Decimal(order.delivery_fee or 0)
    if not shop_flag('shop_distance_fee_enabled'):
        return old_fee, False
    areas = _areas()
    fee = new_delivery_fee(old_fee, area_extra_for_text(old_addr, areas)[0],
                           area_extra_for_text(new_addr, areas)[0], getattr(order, 'pro_delivery_waived', ZERO))
    return fee, fee != old_fee


def distance_plan(order, new_addr, coords):
    """Store per-km fee / max km rakhta ho to naye pin se fee. Lautata hai (fee ya None, error).
    fee None = distance se fee nahi badalti (switch OFF / store per-km nahi rakhta) -> fee_for_change wala hisab.
    error = badlav nahi ho sakta (pin chahiye / store itni door deliver nahi karta)."""
    from ..module_config.shop_flags import shop_flag
    if not shop_flag('shop_distance_fee_enabled') or not order.vendor_id:
        return None, ''
    from . import store_orders
    from .delivery_pricing import compute_fee, haversine_km
    prof = store_orders.get_store_profile(order.vendor_id)
    if not prof or prof.lat is None or prof.lng is None:
        return None, ''
    per_km, max_km = Decimal(prof.eff_fee_per_km or 0), prof.max_delivery_km
    if not (per_km > 0 or max_km):
        return None, ''
    if not coords:
        return None, 'Is store ki fee doori ke hisab se hai. "Pin my current location" dabayen, phir address update karein.'
    km = round(haversine_km(prof.lat, prof.lng, coords[0], coords[1]), 1)
    if max_km and Decimal(str(km)) > Decimal(max_km):
        return None, f'{prof.business_name} sirf {max_km} km tak deliver karta hai (aap {km} km door hain).'
    if Decimal(order.delivery_fee or 0) <= 0 or Decimal(getattr(order, 'pro_delivery_waived', 0) or 0) > 0:
        return Decimal(order.delivery_fee or 0), ''
    extra = area_extra_for_text(new_addr, _areas())[0]
    return compute_fee(prof.eff_delivery_fee, per_km, prof.eff_free_radius_km, km, extra), ''


def note_line(old_addr, new_addr, old_fee, new_fee, when):
    s = f"\n📍 {NOTE_TAG} ({when}): {old_addr or '-'} -> {new_addr}"
    if old_fee != new_fee:
        s += f" | Delivery fee Rs. {old_fee:,.0f} -> Rs. {new_fee:,.0f}"
    return s


def notify_vendor(order, old_addr, new_addr, old_fee, new_fee):
    """Store ko in-app khabar (order kabhi nahi rukta: galti sirf log hoti hai)."""
    try:
        if not order.vendor_id:
            return
        from . import store_orders
        from .vendor_access import notify_users
        prof = store_orders.get_store_profile(order.vendor_id)
        if not prof:
            return
        msg = f'New address: {new_addr}'
        if old_fee != new_fee:
            msg += f'\nDelivery fee: Rs. {old_fee:,.0f} -> Rs. {new_fee:,.0f}'
        for target in notify_users(prof):
            store_orders._notify(target, f'📍 Address changed - order #{order.order_no}', msg,
                                 link='/shop/vendor/orders/', kind='sale', category='orders', priority='high')
    except Exception as exc:
        logger.error('address change notify error: %s', exc)
