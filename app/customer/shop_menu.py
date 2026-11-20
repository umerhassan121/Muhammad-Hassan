"""Customer shop: ek shared menu (neeche 5 tab ki bar + Account sheet) - Step 2.

Yahan sirf faisla hota hai (kaun sa tab, kab dikhe, badge, active tab). Shakal
templates/customer_portal/_shop_menu.html mein hai.

Qaidey:
  * Vendor / Rider pages (url_name 'vendor_*' / 'rider_*' ya path /shop/vendor/, /shop/rider/)
    purana chrome (hamburger sidebar) hi rakhte hain - unhe haath nahi lagaya.
  * Cart / Checkout / Place order par bar chhupi rehti hai (wahan ek bara action button hoga).
  * Koi bhi galti ho to page nahi tootta: menu bas nahi dikhta.
"""
import logging

logger = logging.getLogger(__name__)

LEGACY_PREFIXES = ('vendor_', 'rider_')
LEGACY_PATHS = ('/shop/vendor/', '/shop/rider/')

# Vendor / rider ke login-register jaise pages: na neeche ki bar, na customer wala hamburger sidebar
# (us sidebar mein customer ke links hain: Home, Cart, Orders... jo yahan bekar hain).
AUTH_PAGES = {'vendor_register', 'vendor_login', 'rider_login', 'rider_register',
              'rider_forgot_password', 'rider_reset_password'}

# In pages par bar nahi (wahan ek bara Checkout / Place order button hai)
HIDE_BAR_ON = {'cart_view', 'checkout', 'place_order'}

# url_name -> kaun sa tab active dikhe
TAB_FOR_URL = {
    'shop_home': 'home', 'shop_product_detail': 'home',
    'store_list': 'stores', 'store_detail': 'stores', 'mart_home': 'stores',
    'cart_view': 'cart', 'checkout': 'cart', 'place_order': 'cart',
    'my_orders': 'orders', 'order_detail_customer': 'orders', 'order_success_page': 'orders',
    'track_order': 'orders', 'track_live_public': 'orders',
    'my_account': 'account', 'wallet_page': 'account', 'pro_page': 'account',
    'favorites_page': 'account', 'repeat_plans': 'account', 'my_addresses': 'account', 'customer_login': 'account',
    'customer_register': 'account', 'shop_help': 'account', 'shop_faq': 'account',
    'shop_about': 'account', 'shop_returns': 'account', 'shop_terms': 'account',
    'shop_privacy': 'account', 'delete_my_account': 'account',
    'forgot_password': 'account', 'reset_password': 'account', 'verify_otp_later': 'account',
}

# Jari order = abhi tak deliver / cancel nahi hua
ACTIVE_ORDER_STATUSES = ['pending', 'confirmed', 'processing', 'ready', 'partially_delivered']


def _url_name(request):
    match = getattr(request, 'resolver_match', None)
    return getattr(match, 'url_name', None) or ''


def is_menu_page(request):
    """True = naya shared menu (customer page). False = purana chrome (vendor / rider / unknown)."""
    name = _url_name(request)
    if not name:
        return False
    if name.startswith(LEGACY_PREFIXES):
        return False
    path = getattr(request, 'path', '') or ''
    if path.startswith(LEGACY_PATHS):
        return False
    return True


def is_bar_hidden(request):
    return _url_name(request) in HIDE_BAR_ON


def menu_flags(request):
    """Context processor: base_shop.html ko batata hai ke naya menu lagana hai ya purana chrome."""
    try:
        on = is_menu_page(request)
        return {'SHOP_MENU_ON': on, 'SHOP_BAR_ON': on and not is_bar_hidden(request),
                'SHOP_AUTH_PAGE': _url_name(request) in AUTH_PAGES}
    except Exception:
        logger.exception('shop_menu.menu_flags')
        return {'SHOP_MENU_ON': False, 'SHOP_BAR_ON': False, 'SHOP_AUTH_PAGE': False}


def cart_count(request):
    try:
        cart = request.session.get('cart', {}) or {}
        return sum(int(item.get('quantity', 0) or 0) for item in cart.values())
    except Exception:
        return 0


# Rider ne order utha liya / raaste mein hai (DeliveryInfo.status)
ON_THE_WAY_STATUSES = ['picked_up', 'in_transit']


def orders_on_the_way(user):
    """True = kam az kam ek order raaste mein hai (Orders tab par live dot). Kuch bhi ghalat ho to False."""
    try:
        if not getattr(user, 'is_authenticated', False) or not hasattr(user, 'customer_profile'):
            return False
        from app.models import SaleOrder
        return SaleOrder.objects.filter(
            customer=user.customer_profile.customer,
            status__in=ACTIVE_ORDER_STATUSES,
            delivery_info__status__in=ON_THE_WAY_STATUSES,
        ).exists()
    except Exception:
        logger.exception('shop_menu.orders_on_the_way')
        return False


def active_orders_count(user):
    """Login customer ke jari orders ki ginti (badge). Kuch bhi ghalat ho to 0."""
    try:
        if not getattr(user, 'is_authenticated', False) or not hasattr(user, 'customer_profile'):
            return 0
        from app.models import SaleOrder
        return SaleOrder.objects.filter(
            customer=user.customer_profile.customer,
            status__in=ACTIVE_ORDER_STATUSES,
        ).count()
    except Exception:
        logger.exception('shop_menu.active_orders_count')
        return 0


def build_tabs(request, flags):
    """Neeche ki bar ke tab (list of dicts). `flags` = SHOP.* (dict jaisa)."""
    from django.urls import reverse

    def on(key):
        try:
            return bool(flags[key]) if hasattr(flags, '__getitem__') else bool(getattr(flags, key))
        except Exception:
            return True   # flag na mile to feature on maano (default sab on hain)

    user = getattr(request, 'user', None)
    logged_in = bool(getattr(user, 'is_authenticated', False) and hasattr(user, 'customer_profile'))
    current = TAB_FOR_URL.get(_url_name(request), '')
    tabs = [{'key': 'home', 'label': 'Home', 'icon': 'bi-house-door', 'icon_on': 'bi-house-door-fill',
             'url': reverse('shop_home')}]
    if on('shop_stores_enabled'):
        tabs.append({'key': 'stores', 'label': 'Stores', 'icon': 'bi-shop', 'icon_on': 'bi-shop',
                     'url': reverse('store_list')})
    tabs.append({'key': 'cart', 'label': 'Cart', 'icon': 'bi-cart3', 'icon_on': 'bi-cart3',
                 'url': reverse('cart_view'), 'badge': cart_count(request), 'is_cart': True})
    if logged_in:
        tabs.append({'key': 'orders', 'label': 'Orders', 'icon': 'bi-receipt', 'icon_on': 'bi-receipt',
                     'url': reverse('my_orders'), 'badge': active_orders_count(user),
                     'live': orders_on_the_way(user)})
    elif on('order_tracking_enabled'):
        tabs.append({'key': 'orders', 'label': 'Track', 'icon': 'bi-geo-alt', 'icon_on': 'bi-geo-alt-fill',
                     'url': reverse('track_order')})
    tabs.append({'key': 'account', 'label': 'Account', 'icon': 'bi-person', 'icon_on': 'bi-person-fill',
                 'url': reverse('my_account') if logged_in else reverse('customer_login'),
                 'is_account': True})
    for t in tabs:
        t['active'] = (t['key'] == current)
    return tabs
