"""{% load address_book %}{% saved_addresses as addrs %} - login customer ki saved addresses (checkout ke chips ke liye)."""
from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def saved_addresses(context):
    request = context.get('request')
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated or not hasattr(user, 'customer_profile'):
        return []
    try:
        out = []
        for a in user.customer_profile.customer.addresses.all()[:10]:
            out.append({
                'id': a.pk, 'type': a.get_address_type_display(), 'is_default': a.is_default,
                'line': f"{a.address_line_1}, {a.city}",
                'full_name': a.full_name, 'phone': a.phone, 'address_line_1': a.address_line_1,
                'city': a.city, 'postal_code': a.postal_code or '', 'landmark': a.landmark or '',
            })
        return out
    except Exception:
        return []
