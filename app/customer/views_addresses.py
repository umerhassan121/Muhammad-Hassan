"""Customer portal: saved addresses (Home / Office / Other).

- Default address ka text `customer.address` mein bhi copy hota hai, kyunke order wahi padhta hai.
- Naya model/migration nahi: purana CustomerAddress istemal hota hai.
"""
import logging
import re

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..decorators import customer_login_required
from ..models import CustomerAddress
from .views_favorites import current_customer

logger = logging.getLogger(__name__)

MAX_ADDRESSES = 10
PHONE_RE = re.compile(r'^(\+92|92|0)?3\d{9}$')   # checkout wala hi qaida
TYPES = dict(CustomerAddress.ADDRESS_TYPES)


def _sync_customer(customer, addr):
    """Default address ko customer.address / contact_number mein copy karo (order yahin se leta hai)."""
    customer.address = f"{addr.address_line_1}, {addr.city}" + (f", {addr.postal_code}" if addr.postal_code else "")
    customer.contact_number = addr.phone
    customer.save()


def _clear_pin(request):
    """Address badla to purana map pin ab sahi nahi."""
    try:
        request.session.pop('drop_pin', None)
        request.session.modified = True
    except Exception:
        pass


def _back(request, default='my_addresses'):
    return redirect('checkout' if request.POST.get('next') == 'checkout' else default)


@customer_login_required
def my_addresses(request):
    customer = current_customer(request)
    if customer is None:
        return redirect('my_account')
    addrs = list(customer.addresses.all())
    edit = None
    try:
        edit_id = int(request.GET.get('edit', ''))
        edit = next((a for a in addrs if a.pk == edit_id), None)
    except (TypeError, ValueError):
        pass
    return render(request, 'customer_portal/addresses.html', {
        'customer': customer,
        'addresses': addrs,
        'edit': edit,
        'address_types': CustomerAddress.ADDRESS_TYPES,
        'can_add': len(addrs) < MAX_ADDRESSES,
        'max_addresses': MAX_ADDRESSES,
    })


@customer_login_required
@require_POST
def address_save(request):
    customer = current_customer(request)
    if customer is None:
        return redirect('my_account')
    p = request.POST
    full_name = ' '.join((p.get('full_name') or '').split())[:100]
    phone = (p.get('phone') or '').replace(' ', '').replace('-', '')[:15]
    line1 = ' '.join((p.get('address_line_1') or '').split())[:255]
    city = ' '.join((p.get('city') or '').split())[:100]
    postal = (p.get('postal_code') or '').strip()[:10]
    landmark = ' '.join((p.get('landmark') or '').split())[:200]
    a_type = p.get('address_type') if p.get('address_type') in TYPES else 'home'
    pk = p.get('id') or ''

    back = redirect('my_addresses')
    if not (full_name and phone and line1 and city):
        messages.error(request, 'Name, phone, address aur city zaroori hain.')
        return redirect(f"/shop/addresses/?edit={pk}" if pk.isdigit() else 'my_addresses')
    if not PHONE_RE.match(phone):
        messages.error(request, 'Sahi phone number daalein.')
        return redirect(f"/shop/addresses/?edit={pk}" if pk.isdigit() else 'my_addresses')
    if len(line1) < 10:
        messages.error(request, 'Address thora mukammal likhein (kam az kam 10 harf).')
        return redirect(f"/shop/addresses/?edit={pk}" if pk.isdigit() else 'my_addresses')

    try:
        if pk.isdigit():
            addr = get_object_or_404(CustomerAddress, pk=int(pk), customer=customer)
        else:
            if customer.addresses.count() >= MAX_ADDRESSES:
                messages.error(request, f'Zyada se zyada {MAX_ADDRESSES} addresses save ho sakte hain.')
                return back
            addr = CustomerAddress(customer=customer)
            addr.is_default = not customer.addresses.exists()   # pehla address khud default
        was_default = addr.is_default
        addr.address_type, addr.full_name, addr.phone = a_type, full_name, phone
        addr.address_line_1, addr.city, addr.postal_code, addr.landmark = line1, city, postal, landmark
        if p.get('make_default'):
            addr.is_default = True
        addr.save()
        if addr.is_default:
            _sync_customer(customer, addr)
            if not was_default or p.get('make_default'):
                _clear_pin(request)
        messages.success(request, 'Address save ho gaya.')
    except Exception as exc:
        logger.error('Address save error: %s', exc)
        messages.error(request, 'Address save nahi ho saka. Dobara koshish karein.')
    return back


@customer_login_required
@require_POST
def address_set_default(request, pk):
    customer = current_customer(request)
    if customer is None:
        return redirect('my_account')
    addr = get_object_or_404(CustomerAddress, pk=pk, customer=customer)
    try:
        if not addr.is_default:
            addr.is_default = True
            addr.save()
            _sync_customer(customer, addr)
            _clear_pin(request)
        messages.success(request, 'Delivery address badal gaya.')
    except Exception as exc:
        logger.error('Address default error: %s', exc)
        messages.error(request, 'Address nahi badal saka.')
    return _back(request)


@customer_login_required
@require_POST
def address_delete(request, pk):
    customer = current_customer(request)
    if customer is None:
        return redirect('my_account')
    addr = get_object_or_404(CustomerAddress, pk=pk, customer=customer)
    try:
        was_default = addr.is_default
        addr.delete()
        if was_default:
            nxt = customer.addresses.order_by('-created_at').first()
            if nxt:
                nxt.is_default = True
                nxt.save()
                _sync_customer(customer, nxt)
                _clear_pin(request)
        messages.success(request, 'Address hata diya gaya.')
    except Exception as exc:
        logger.error('Address delete error: %s', exc)
        messages.error(request, 'Address nahi hat saka.')
    return redirect('my_addresses')
