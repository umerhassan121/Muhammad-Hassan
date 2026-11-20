"""{% vendor_nav %} - vendor pages par shared menu (Step 2).

base_shop.html mein ek hi jagah lagta hai. Vendor login nahi ho, ya login/register page ho, to kuch nahi dikhata,
is liye customer pages par koi farq nahi parta. Koi bhi galti ho to page nahi tootta - menu bas nahi dikhta.
"""
import logging

from django import template

from app.customer.vendor_nav import build_nav

register = template.Library()
logger = logging.getLogger(__name__)

# In pages par menu nahi (abhi login nahi / register ho raha hai)
HIDE_ON = {'vendor_login', 'vendor_register'}


def _badges(vendor):
    """Orders aur disputes ke badge. Kuch bhi ghalat ho to 0."""
    out = {}
    try:
        from app.models import SaleOrder
        out['new_orders'] = SaleOrder.objects.filter(vendor=vendor, status='pending').count()
    except Exception:
        logger.exception('vendor_nav: new_orders badge')
    try:
        from app.customer.disputes import needs_response_count
        out['dispute_pending'] = needs_response_count('vendor', vendor)
    except Exception:
        logger.exception('vendor_nav: dispute badge')
    return out


def vendor_nav_context(request):
    """Menu ka data, ya None agar yahan menu nahi dikhana. (Test ke liye alag function.)"""
    user = getattr(request, 'user', None)
    match = getattr(request, 'resolver_match', None)
    current = getattr(match, 'url_name', None) or ''
    if not current.startswith('vendor_') or current in HIDE_ON:
        return None
    if not getattr(user, 'is_authenticated', False):
        return None
    from app.customer.vendor_access import get_vendor_profile, vendor_role
    profile = get_vendor_profile(user)
    if profile is None:
        return None
    role = vendor_role(user)
    badges = _badges(profile.vendor) if role in ('owner', 'manager', 'orders') else {}
    data = build_nav(role, current=current, is_approved=bool(getattr(profile, 'is_approved', False)), badges=badges)
    return data if data['groups'] else None


@register.inclusion_tag('customer_portal/vendor/_vendor_nav.html', takes_context=True)
def vendor_nav(context):
    request = context.get('request')
    try:
        nav = vendor_nav_context(request) if request is not None else None
    except Exception:
        logger.exception('vendor_nav')
        nav = None
    return {'nav': nav}
