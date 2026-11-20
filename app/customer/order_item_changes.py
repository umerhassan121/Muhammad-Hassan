"""Mart / store order: vendor ek item replace ya remove kare (out of stock hone par).

Sirf order accept se pehle-pehle ya tayyar hone tak (pending / confirmed / processing).
- remove  : item hata do; bill ghatta hai; order mein kam az kam ek item bacha rehna chahiye
            (warna order reject karein).
- replace : usi store ka dusra live, stock wala product, usi qty par, uski apni price par.
Dono mein: reservation theek hoti hai, wallet se zyada di hui raqam wapas, order notes mein line,
aur customer ko notification. Sab kuch ek transaction mein; galti par OrderChangeError.
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum

logger = logging.getLogger(__name__)
EDITABLE_STATUSES = ('pending', 'confirmed', 'processing')
ZERO = Decimal('0')


class OrderChangeError(Exception):
    pass


def _check(order, vendor):
    if order.vendor_id != vendor.id:
        raise OrderChangeError('This order does not belong to your store.')
    if order.status not in EDITABLE_STATUSES:
        raise OrderChangeError('Items can only be changed before the order is ready.')


def _release(item):
    """Item ki reserved stock wapas (agar reserve thi)."""
    from ..models import Inventory
    if item.reserved:
        Inventory.objects.filter(product_id=item.product_id, warehouse=item.order.warehouse).update(
            reserved_stock=F('reserved_stock') - item.qty)


def _settle_wallet(order):
    """Naya total wallet se di hui raqam se kam ho to farq wallet mein wapas (aur wallet_paid ghat jata hai)."""
    from ..models import WalletTransaction
    from .store_orders import order_payable_total
    paid = Decimal(order.wallet_paid or 0)
    new_total = order_payable_total(order)
    if paid <= new_total or not order.customer_id:
        return ZERO
    if not WalletTransaction.objects.filter(order=order, kind='spend').exists():
        return ZERO
    back = paid - new_total
    # (order, kind) unique hai: pehle se 'adjust' ho to us mein jama karte hain
    tx, created = WalletTransaction.objects.get_or_create(
        order=order, kind='adjust',
        defaults={'customer_id': order.customer_id, 'amount': back,
                  'note': f'Item change returned: order #{order.order_no}'})
    if not created:
        tx.amount = Decimal(tx.amount) + back
        tx.save(update_fields=['amount'])
    order.wallet_paid = new_total
    return back


def _finish(order, line, user, title):
    from . import tax
    tax.stamp_order(order)
    back = _settle_wallet(order)
    order.notes = (order.notes or '') + f'\n{line}'
    if back > 0:
        order.notes += f'\nRs. {back:,.0f} returned to the customer wallet.'
    order.save(update_fields=['notes', 'wallet_paid', 'gst_amount', 'updated_at'])
    try:
        from .store_orders import _customer_user, _notify, order_cash_due
        due = f' Cash to pay: Rs. {order_cash_due(order):,.0f}.' if (order.payment_method or 'cod') == 'cod' else ''
        _notify(_customer_user(order), f'{title} (order #{order.order_no})', line + due,
                link=None, kind='sale', category='orders', priority='high')
    except Exception:
        logger.exception('order_item_changes notify')
    return back


def candidates(item, limit=6):
    """Replace ke liye mashwara: usi store ka, usi category ka, stock wala, order mein pehle se nahi."""
    from ..models import Product
    from .views_customer_portal import get_product_final_price
    order = item.order
    in_order = list(order.items.values_list('product_id', flat=True))
    qs = Product.objects.filter(is_active=True, approval_status='approved', vendor_id=order.vendor_id)
    if item.product.category_id:
        qs = qs.filter(category_id=item.product.category_id)
    qs = qs.exclude(pk__in=in_order).annotate(stock_sum=Sum('inventory__stock')).filter(
        stock_sum__gte=item.qty).order_by('name')[:limit]
    return [{'id': p.id, 'name': p.name, 'price': get_product_final_price(p)} for p in qs]


@transaction.atomic
def remove_item(order, item_id, vendor, user=None):
    from ..models import SaleOrder
    order = SaleOrder.objects.select_for_update().get(pk=order.pk)
    _check(order, vendor)
    item = order.items.select_related('product').filter(pk=item_id).first()
    if item is None:
        raise OrderChangeError('That item is not in this order.')
    if order.items.count() <= 1:
        raise OrderChangeError('This is the only item. Reject the order instead.')
    amount, name = item.total_amt, item.product.name
    _release(item)
    item.delete()
    return _finish(order, f'Removed out-of-stock item: {name} (-Rs. {amount:,.0f}).', user, 'Item removed')


@transaction.atomic
def replace_item(order, item_id, new_product_id, vendor, user=None):
    from ..models import Inventory, Product, SaleOrder, SaleOrderItem
    from .views_customer_portal import get_product_final_price
    order = SaleOrder.objects.select_for_update().get(pk=order.pk)
    _check(order, vendor)
    item = order.items.select_related('product').filter(pk=item_id).first()
    if item is None:
        raise OrderChangeError('That item is not in this order.')
    new = Product.objects.filter(pk=new_product_id, is_active=True, approval_status='approved',
                                 vendor_id=order.vendor_id).first()
    if new is None:
        raise OrderChangeError('Choose a live product from your own store.')
    if order.items.filter(product=new, options_key='').exclude(pk=item.pk).exists():
        raise OrderChangeError('That product is already in this order.')
    inv = Inventory.objects.select_for_update().filter(product=new, warehouse=order.warehouse).first()
    if inv is None or inv.available_stock < item.qty:
        raise OrderChangeError(f'Not enough stock for {new.name}.')
    old_name, old_total, was_reserved, qty = item.product.name, item.total_amt, item.reserved, item.qty
    _release(item)
    price = Decimal(str(get_product_final_price(new))).quantize(Decimal('0.01'))
    total = Decimal(qty) * price
    # save() ke bajaye update(): save() naye product par purani reservation galat chhoota
    SaleOrderItem.objects.filter(pk=item.pk).update(
        product=new, price=price, total_amt=total, options_text='', options_key='', options_extra=0,
        reserved=was_reserved)
    if was_reserved:
        Inventory.objects.filter(pk=inv.pk).update(reserved_stock=F('reserved_stock') + qty)
    diff = total - old_total
    sign = '+' if diff >= 0 else '-'
    return _finish(order, f'Replaced {old_name} with {new.name} ({sign}Rs. {abs(diff):,.0f}).', user, 'Item replaced')
