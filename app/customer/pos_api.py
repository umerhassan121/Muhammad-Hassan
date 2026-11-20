"""POS / printer API helpers: token auth + order payload.

- Token: "Authorization: Bearer <token>" header. DB mein sirf SHA-256 hash save hota hai.
- order_payload(): receipt (HTML + ESC/POS) aur API feed ka ek hi format. Customer ka phone / address
  yahan ek hi jagah privacy ki shartein (vendor portal ke Orders page jaisi) se tay hota hai.
"""
import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone

from . import store_orders

FEED_LIMIT = 100
TOKEN_PREFIX = 'pos_'
FINAL_STATUSES = ('delivered', 'cancelled', 'returned', 'invoiced')


def _hash(raw):
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def create_token(profile):
    """Naya token banao (purana, agar ho, badal jata hai). Asal token sirf yahan wapas milta hai."""
    from ..models import VendorPosToken
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    VendorPosToken.objects.update_or_create(
        profile=profile,
        defaults={'token_hash': _hash(raw), 'prefix': raw[:8], 'last_used_at': None},
    )
    return raw


def revoke_token(profile):
    from ..models import VendorPosToken
    VendorPosToken.objects.filter(profile=profile).delete()


def _bearer(request):
    header = request.META.get('HTTP_AUTHORIZATION', '')
    parts = header.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == 'bearer':
        return parts[1].strip()
    return ''


def profile_for_request(request):
    """Bearer token se VendorProfile (approved store). Ghalat / missing token ya unapproved store -> None."""
    raw = _bearer(request)
    if not raw or len(raw) > 200:
        return None
    from ..models import VendorPosToken
    rec = (VendorPosToken.objects.select_related('profile__vendor', 'profile__user')
           .filter(token_hash=_hash(raw)).first())
    if rec is None or not rec.profile.is_approved:
        return None
    now = timezone.now()
    if rec.last_used_at is None or now - rec.last_used_at > timedelta(minutes=1):
        VendorPosToken.objects.filter(pk=rec.pk).update(last_used_at=now)
    return rec.profile


def _money(value):
    return f'{value:.2f}'


def order_payload(order, items, delivery=None):
    """Order ka dict (JSON-safe). items = SaleOrderItem list, delivery = DeliveryInfo ya None."""
    final = order.status in FINAL_STATUSES
    try:
        recent = (timezone.now() - order.order_date) <= timedelta(days=2)
    except Exception:
        recent = False
    show_contact = (not final) or (order.status == 'cancelled' and recent)
    show_address = (not final) and not (delivery is not None and delivery.rider_id)
    customer = order.customer
    return {
        'id': order.pk,
        'order_no': order.order_no,
        'status': order.status,
        'created_at': order.order_date.isoformat() if order.order_date else None,
        'scheduled_for': order.scheduled_for.isoformat() if order.scheduled_for else None,
        'prep_minutes': order.prep_minutes,
        'customer': {
            'name': customer.name,
            'phone': (customer.contact_number or '') if show_contact else '',
            'address': order.ship_address() if show_address else '',
        },
        'items': [{
            'name': it.product.name,
            'qty': it.qty,
            'unit_price': _money(it.price),
            'options': it.options_text or '',
            'note': it.note or '',
        } for it in items],
        'subtotal': _money(order.total_after_discount()),
        'delivery_fee': _money(order.delivery_fee or 0),
        'total': _money(store_orders.order_payable_total(order)),
        'payment_method': order.payment_method or 'cod',
        'cash_due': _money(store_orders.order_cash_due(order)),
        'wallet_paid': _money(order.wallet_paid or 0),
    }
