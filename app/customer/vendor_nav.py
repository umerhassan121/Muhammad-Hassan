"""Vendor portal ka navigation naqsha (Step 1).

Ek hi jagah par tay hota hai ke vendor ko kaun se menu items, kis group mein, kis role ko dikhen.
Templates (Step 2 se) sirf `build_nav(...)` ka nateeja dikhayenge - buttons ab har page par alag se nahi likhne parenge.

Role ke rules `vendor_access.role_can_open` se aate hain (owner / manager / orders), yahan dobara nahi likhe.
Is file mein koi database ya request ka kaam nahi - sirf data aur chhote functions, isliye test aasaan hai.
"""
from .vendor_access import role_can_open

# Item: url_name, label, icon (bootstrap-icons), flag (shop setting jo ON honi chahiye),
#       needs_approved (sirf approved store), badge (badge ka naam), also (is item ke andar aane wale dusre url names)
NAV_GROUPS = [
    {
        'key': 'orders', 'label': 'Orders', 'icon': 'bi-bag-check',
        'also': {'vendor_order_action', 'vendor_order_receipt', 'vendor_order_escpos', 'vendor_assign_rider',
                 'vendor_orders_poll', 'vendor_pause', 'vendor_dispute_detail'},
        'items': [
            {'url_name': 'vendor_orders', 'label': 'Orders', 'icon': 'bi-bag-check', 'badge': 'new_orders',
             'also': {'vendor_order_action', 'vendor_order_receipt', 'vendor_order_escpos', 'vendor_assign_rider',
                      'vendor_orders_poll', 'vendor_pause'}},
            {'url_name': 'vendor_disputes', 'label': 'Disputes', 'icon': 'bi-exclamation-triangle',
             'badge': 'dispute_pending', 'also': {'vendor_dispute_detail'}},
        ],
    },
    {
        'key': 'menu', 'label': 'Menu', 'icon': 'bi-list-stars',
        'items': [
            {'url_name': 'vendor_menu', 'label': 'Menu', 'icon': 'bi-list-stars',
             'also': {'vendor_product_edit', 'vendor_product_options', 'vendor_product_toggle', 'vendor_product_action'}},
            {'url_name': 'vendor_product_add', 'label': 'Add products', 'icon': 'bi-plus-circle', 'needs_approved': True},
            {'url_name': 'vendor_item_schedule', 'label': 'Item schedule', 'icon': 'bi-clock'},
            {'url_name': 'vendor_menu_quality', 'label': 'Menu quality', 'icon': 'bi-check2-circle'},
        ],
    },
    {
        'key': 'marketing', 'label': 'Marketing', 'icon': 'bi-megaphone',
        'items': [
            {'url_name': 'vendor_offers', 'label': 'Offers', 'icon': 'bi-tag', 'needs_approved': True},
            {'url_name': 'vendor_deals', 'label': 'Deals', 'icon': 'bi-gift', 'needs_approved': True,
             'flag': 'vendor_deals_enabled', 'also': {'vendor_deal_end'}},
            {'url_name': 'vendor_promote', 'label': 'Promote', 'icon': 'bi-megaphone', 'needs_approved': True,
             'flag': 'shop_sponsored_enabled'},
        ],
    },
    {
        'key': 'money', 'label': 'Money', 'icon': 'bi-cash-stack',
        'items': [
            {'url_name': 'vendor_reports', 'label': 'Reports', 'icon': 'bi-graph-up'},
            {'url_name': 'vendor_my_performance', 'label': 'Performance', 'icon': 'bi-speedometer2'},
            {'url_name': 'vendor_statements', 'label': 'Statements', 'icon': 'bi-receipt',
             'also': {'vendor_statement', 'vendor_statement_pdf'}},
            {'url_name': 'vendor_payouts', 'label': 'Payouts', 'icon': 'bi-wallet2', 'also': {'vendor_payout_cancel'}},
        ],
    },
    {
        'key': 'store', 'label': 'Store', 'icon': 'bi-shop',
        'items': [
            {'url_name': 'vendor_store_settings', 'label': 'Store settings', 'icon': 'bi-gear',
             'also': {'vendor_set_location'}},
            {'url_name': 'vendor_branches', 'label': 'Branches', 'icon': 'bi-diagram-3',
             'also': {'vendor_branch_action', 'vendor_branch_copy'}},
            {'url_name': 'vendor_staff', 'label': 'Staff', 'icon': 'bi-people', 'also': {'vendor_staff_action'}},
            {'url_name': 'vendor_documents', 'label': 'Documents', 'icon': 'bi-file-earmark-text'},
            {'url_name': 'vendor_pos', 'label': 'POS / Printer', 'icon': 'bi-printer'},
        ],
    },
    {
        'key': 'help', 'label': 'Help', 'icon': 'bi-question-circle',
        'items': [
            {'url_name': 'vendor_help', 'label': 'Help & Support', 'icon': 'bi-question-circle',
             'also': {'vendor_support', 'vendor_support_detail'}},
            {'url_name': 'vendor_reviews', 'label': 'Reviews', 'icon': 'bi-star', 'also': {'vendor_reply_review'}},
        ],
    },
]

HOME_URL = 'vendor_dashboard'
LOGOUT_URL = 'vendor_logout'

# Phone ki neeche wali bar: Home, Orders, Menu, Money, More (More = baqi groups)
TAB_GROUPS = ('orders', 'menu', 'money')
MORE_GROUPS = ('marketing', 'store', 'help')


def _default_flag(name):
    from ..module_config.shop_flags import shop_flag
    return shop_flag(name)


def _item_visible(item, role, is_approved, flag):
    if not role_can_open(role, item['url_name']):
        return False
    if item.get('needs_approved') and not is_approved:
        return False
    if item.get('flag') and not flag(item['flag']):
        return False
    return True


def build_nav(role, current=None, is_approved=True, flag=None, badges=None):
    """Is vendor (role) ke liye menu tayyar karo.

    role        : 'owner' / 'manager' / 'orders' (vendor_access.vendor_role se)
    current     : abhi khuli page ka url_name (request.resolver_match.url_name)
    is_approved : store approved hai ya nahi
    flag        : callable(name) -> bool (shop settings); None ho to asli shop_flag
    badges      : {'new_orders': 3, 'dispute_pending': 1}

    Wapas deta hai:
      groups : sirf wo groups jin mein kam az kam 1 item dikhe (har item mein active, badge)
      home   : Home ka item
      tabs   : phone ki bottom bar (Home, Orders, Menu, Money, More)
      more   : "More" mein aane wale groups
      logout : logout ka url_name
    """
    if role not in ('owner', 'manager', 'orders'):
        return {'groups': [], 'home': None, 'tabs': [], 'more': [], 'logout': LOGOUT_URL}
    flag = flag or _default_flag
    badges = badges or {}

    groups = []
    for g in NAV_GROUPS:
        items = []
        for it in g['items']:
            if not _item_visible(it, role, is_approved, flag):
                continue
            names = {it['url_name']} | set(it.get('also', ()))
            items.append({
                'url_name': it['url_name'], 'label': it['label'], 'icon': it['icon'],
                'active': current in names,
                'badge': badges.get(it.get('badge')) or 0,
            })
        if not items:
            continue
        group_names = {i['url_name'] for i in items} | set(g.get('also', ())) | \
            {n for it in g['items'] for n in it.get('also', ())}
        groups.append({
            'key': g['key'], 'label': g['label'], 'icon': g['icon'], 'items': items,
            'landing': items[0]['url_name'],
            'active': current in group_names,
            'badge': sum(i['badge'] for i in items),
        })

    by_key = {g['key']: g for g in groups}
    home = {'url_name': HOME_URL, 'label': 'Home', 'icon': 'bi-house-door', 'active': current == HOME_URL}

    tabs = [dict(home, key='home')]
    for key in TAB_GROUPS:
        g = by_key.get(key)
        if g:
            tabs.append({'key': key, 'label': g['label'], 'icon': g['icon'], 'url_name': g['landing'],
                         'active': g['active'], 'badge': g['badge']})
    more = [by_key[k] for k in MORE_GROUPS if k in by_key]
    if more:
        tabs.append({'key': 'more', 'label': 'More', 'icon': 'bi-three-dots', 'url_name': None,
                     'active': any(g['active'] for g in more), 'badge': sum(g['badge'] for g in more)})

    return {'groups': groups, 'home': home, 'tabs': tabs, 'more': more, 'logout': LOGOUT_URL}
