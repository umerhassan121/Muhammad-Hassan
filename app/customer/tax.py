"""GST / sales tax (Pakistan) - prices TAX-INCLUSIVE.

Shop ki qeematein pehle se tax shamil hoti hain (Pakistan mein aam retail tareeqa), is liye GST total mein
IZAFA nahi hota: sirf bill par "includes GST" ka hissa dikhta hai aur order par mehfooz hota hai.

Settings > Shop mein: shop_gst_enabled (OFF = kuch nahi badalta), shop_gst_rate (%), shop_gst_label,
shop_gst_ntn. Product.gst_rate khali = shop ka rate, 0 = tax se mustasna, warna us product ka apna rate.
Rate / chhoot ka faisla aap ke accountant ka hai - yahan sirf hisaab aur dikhana hai.
Coupon discount hone par tax bhi usi tanasub se kam hota hai. Koi bhi galti ho to order nahi rukta.
"""
import logging
from decimal import ROUND_HALF_UP, Decimal

logger = logging.getLogger(__name__)
ZERO = Decimal('0.00')
CENT = Decimal('0.01')


def _setting(key, default=''):
    from ..models import SystemSetting
    row = SystemSetting.objects.filter(setting_key=key).values_list('setting_value', flat=True).first()
    return default if row is None else row


def config():
    """{'enabled', 'rate' (Decimal %), 'label', 'ntn'}. Galti par band maana jata hai."""
    try:
        from ..shop_flags import shop_flag
        if not shop_flag('shop_gst_enabled'):
            return {'enabled': False, 'rate': ZERO, 'label': 'GST', 'ntn': ''}
        try:
            rate = max(Decimal(str(_setting('shop_gst_rate', '0')).strip() or '0'), ZERO)
        except Exception:
            rate = ZERO
        return {'enabled': True, 'rate': min(rate, Decimal('100')),
                'label': (_setting('shop_gst_label', 'GST') or 'GST').strip()[:20],
                'ntn': (_setting('shop_gst_ntn', '') or '').strip()[:40]}
    except Exception:
        logger.exception('tax.config')
        return {'enabled': False, 'rate': ZERO, 'label': 'GST', 'ntn': ''}


def rate_for(product, cfg):
    own = getattr(product, 'gst_rate', None)
    return Decimal(own) if own is not None else cfg['rate']


def included(amount, rate):
    """Tax-inclusive amount mein se tax ka hissa: amount * r / (100 + r)."""
    amount, rate = Decimal(str(amount or 0)), Decimal(str(rate or 0))
    if amount <= 0 or rate <= 0:
        return ZERO
    return (amount * rate / (Decimal(100) + rate)).quantize(CENT, rounding=ROUND_HALF_UP)


def _after_discount(gst, base, discount):
    discount = Decimal(str(discount or 0))
    if gst <= 0 or discount <= 0 or base <= 0:
        return gst
    factor = max(base - discount, ZERO) / base
    return (gst * factor).quantize(CENT, rounding=ROUND_HALF_UP)


def cart_gst(cart_items, discount=0):
    """Cart page ke liye: {'enabled', 'label', 'rate', 'amount'}. cart_items = calculate_cart_data ki list."""
    cfg = config()
    out = {'enabled': cfg['enabled'], 'label': cfg['label'], 'rate': cfg['rate'], 'amount': ZERO}
    if not cfg['enabled']:
        return out
    try:
        gst, base = ZERO, ZERO
        for it in cart_items:
            line = Decimal(str(it.get('subtotal', 0) or 0))
            base += line
            gst += included(line, rate_for(it.get('product_obj'), cfg))
        out['amount'] = _after_discount(gst, base, discount)
    except Exception:
        logger.exception('tax.cart_gst')
    return out


def stamp_order(order):
    """Order ki items par rate likho aur order.gst_amount set karo (items ban jane ke BAAD). Kul tax wapas."""
    cfg = config()
    if not cfg['enabled']:
        return ZERO
    try:
        from ..models import SaleOrder, SaleOrderItem
        gst, base = ZERO, ZERO
        for it in order.items.select_related('product'):
            rate = rate_for(it.product, cfg)
            SaleOrderItem.objects.filter(pk=it.pk).update(gst_rate=rate)
            base += it.total_amt
            gst += included(it.total_amt, rate)
        gst = _after_discount(gst, base, order.discount_value)
        SaleOrder.objects.filter(pk=order.pk).update(gst_amount=gst)
        order.gst_amount = gst
        return gst
    except Exception:
        logger.exception('tax.stamp_order')
        return ZERO
