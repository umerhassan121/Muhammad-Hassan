"""{% shop_theme as SHOP_THEME %} - customer ne jo shop theme chuni, uska naam (cookie 'shop_theme' se).

Maximalism (purani theme) default hai. Vendor / Rider pages par khali string milti hai (wahan koi theme nahi).
Cookie mein koi ghalat / anjaan naam ho to bhi 'maximal' hi milta hai, is liye page kabhi nahi tootta.
"""
from django import template

register = template.Library()

THEMES = ('maximal', 'glass', 'clay', 'liquid', 'spatial', 'bento', 'soft', 'minimal', 'market', 'luxury', 'fresh')
DEFAULT_THEME = 'maximal'
COOKIE_NAME = 'shop_theme'


@register.simple_tag(takes_context=True)
def shop_theme(context):
    request = context.get('request')
    path = getattr(request, 'path', '') or ''
    if '/shop/vendor/' in path or '/shop/rider/' in path:
        return ''
    try:
        value = (request.COOKIES.get(COOKIE_NAME) or '').strip().lower()
    except Exception:
        value = ''
    return value if value in THEMES else DEFAULT_THEME
