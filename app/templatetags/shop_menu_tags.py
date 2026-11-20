"""{% shop_menu %} - customer pages par neeche 5 tab ki bar + Account sheet (Step 2).

base_shop.html mein ek hi jagah lagta hai. Vendor / Rider pages par kuch nahi dikhata
(wahan purana menu hi rehta hai). Koi bhi galti ho to page nahi tootta - menu bas nahi dikhta.
"""
import logging

from django import template

from app.customer import shop_menu as sm

register = template.Library()
logger = logging.getLogger(__name__)

PASS_THROUGH = ('request', 'user', 'SHOP', 'LANGUAGES', 'LANG_CODE', 'company_name', 'company_whatsapp_url',
                'company_contact_number', 'company_email', 'company_website')


@register.inclusion_tag('customer_portal/_shop_menu.html', takes_context=True)
def shop_menu(context):
    request = context.get('request')
    out = {'sm_tabs': [], 'sm_show_bar': False, 'sm_logged_in': False}
    try:
        if request is not None and sm.is_menu_page(request):
            out['sm_tabs'] = sm.build_tabs(request, context.get('SHOP'))
            out['sm_show_bar'] = not sm.is_bar_hidden(request)
            out['sm_logged_in'] = bool(getattr(request.user, 'is_authenticated', False)
                                       and hasattr(request.user, 'customer_profile'))
    except Exception:
        logger.exception('shop_menu')
        out['sm_tabs'] = []
        out['sm_show_bar'] = False
    for key in PASS_THROUGH:
        out[key] = context.get(key)
    return out
