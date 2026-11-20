"""Vendor dashboard ke KPI cards aur alerts ke qaide (Step 3).

Django ke baghair chalta hai - sirf numbers aur chhote dicts, isliye test aasaan hai.
View `perf_metrics` ka nateeja deta hai, yahan sirf dikhane ki shakal banti hai.
"""
from . import vendor_perf_rules as rules


def _pct(v):
    return '-' if v is None else '%s%%' % ('%d' % v if float(v) == int(v) else '%.1f' % v)


def kpi_cards(today, week):
    """4 cards: aaj ke orders, 7 din ka accept rate, 7 din ki rating, store quality score.

    today / week = perf_metrics ke dict (ya None). Data na ho to '-' dikhta hai, galat 0 nahi.
    """
    today = today or {}
    week = week or {}
    score = week.get('score')
    label, tone = rules.score_label(score)
    rating = week.get('rating')
    accept = week.get('accept_rate')
    return [
        {'key': 'orders', 'label': 'Orders today', 'value': str(today.get('orders', 0)),
         'sub': '%d waiting for you' % today.get('pending', 0) if today.get('pending') else 'All handled',
         'tone': 'warn' if today.get('pending') else 'good', 'url_name': 'vendor_orders'},
        {'key': 'accept', 'label': 'Accept rate (7 days)', 'value': _pct(accept),
         'sub': '%d orders' % week.get('orders', 0),
         'tone': 'na' if accept is None else ('good' if accept >= 90 else 'warn' if accept >= 70 else 'bad'),
         'url_name': 'vendor_my_performance'},
        {'key': 'rating', 'label': 'Rating (7 days)', 'value': '-' if rating is None else '%.1f / 5' % rating,
         'sub': '%d reviews' % week.get('rating_n', 0),
         'tone': 'na' if rating is None else ('good' if rating >= 4.2 else 'warn' if rating >= 3.5 else 'bad'),
         'url_name': 'vendor_reviews'},
        {'key': 'score', 'label': 'Store quality', 'value': '-' if score is None else '%d / 100' % round(score),
         'sub': label, 'tone': tone, 'url_name': 'vendor_my_performance'},
    ]


def alerts(new_orders=0, dispute_pending=0, out_count=0, low_count=0, is_approved=True, is_paused=False):
    """Jin cheezon par vendor ko abhi dhyan dena hai. Khali list = sab theek.

    Har alert: level ('danger' / 'warn' / 'info'), text, url_name, cta.
    """
    out = []
    if not is_approved:
        out.append({'level': 'info', 'text': 'Your store is waiting for admin approval.',
                    'url_name': 'vendor_help', 'cta': 'Help'})
    if new_orders:
        out.append({'level': 'danger',
                    'text': '%d new order%s waiting for your answer.' % (new_orders, '' if new_orders == 1 else 's'),
                    'url_name': 'vendor_orders', 'cta': 'Open orders'})
    if dispute_pending:
        out.append({'level': 'danger',
                    'text': '%d dispute%s need%s your reply.' % (
                        dispute_pending, '' if dispute_pending == 1 else 's', 's' if dispute_pending == 1 else ''),
                    'url_name': 'vendor_disputes', 'cta': 'Reply'})
    if out_count:
        out.append({'level': 'warn',
                    'text': '%d product%s sold out.' % (out_count, '' if out_count == 1 else 's'),
                    'url_name': 'vendor_menu', 'cta': 'Open menu'})
    if low_count:
        out.append({'level': 'warn',
                    'text': '%d product%s running low.' % (low_count, '' if low_count == 1 else 's'),
                    'url_name': 'vendor_menu', 'cta': 'Open menu'})
    if is_paused:
        out.append({'level': 'warn', 'text': 'Busy mode is ON - new orders are paused.',
                    'url_name': 'vendor_dashboard', 'cta': ''})
    return out
