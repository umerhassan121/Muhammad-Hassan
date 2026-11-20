"""Notification system ke pure rules (Django ka koi import nahi - seedha test ho sakte hain).

- TEMPLATES: har event ka title/body/type/category/priority/link ek jagah (har jagah ek jaisa style).
- Grouping: ek event baar baar ho to ek card ("5 new orders") - group_key + group_text.
- Priority, snooze ki tareekh, aur list ke filters ki safai (parse_filters).
"""
import re
from datetime import datetime, time, timedelta

PRIORITIES = [('critical', 'Critical'), ('high', 'High'), ('normal', 'Normal'), ('low', 'Low')]
PRIORITY_RANK = {'critical': 0, 'high': 1, 'normal': 2, 'low': 3}
PRIORITY_KEYS = [k for k, _ in PRIORITIES]
TYPE_KEYS = ['info', 'success', 'warning', 'danger', 'sale', 'installment', 'stock', 'payment']

# (id, naam, bootstrap icon) - ERP wali purani + marketplace wali nayi
CATEGORIES = [
    ('all', 'All', 'bi-bell'),
    ('orders', 'Orders', 'bi-bag-check'),
    ('vendors', 'Vendors', 'bi-shop'),
    ('riders', 'Riders', 'bi-bicycle'),
    ('disputes', 'Disputes', 'bi-exclamation-triangle'),
    ('payments', 'Payments', 'bi-currency-rupee'),
    ('sales', 'Sales', 'bi-cart'),
    ('installments', 'Installments', 'bi-calendar'),
    ('stock', 'Stock', 'bi-box'),
    ('security', 'Security', 'bi-shield-lock'),
    ('marketing', 'Marketing', 'bi-megaphone'),
    ('system', 'System', 'bi-gear'),
]
CATEGORY_KEYS = [c for c, _n, _i in CATEGORIES]

DEFAULT_GROUP_WINDOW_MIN = 30

# event -> template. {placeholders} ctx se bharte hain. 'group' = group_key ka template (khali = grouping nahi).
TEMPLATES = {
    'vendor_registered': {
        'title': '🏢 New vendor registered',
        'body': '{business} ({city}), {owner}: {status}.',
        'type': 'warning', 'category': 'vendors', 'priority': 'high',
    },
    'vendor_docs_uploaded': {
        'title': '📄 Vendor documents uploaded',
        'body': '{business} uploaded {document}. Review it.',
        'type': 'info', 'category': 'vendors', 'priority': 'normal',
        'group': 'vdocs:{store_id}',
        'group_title': '📄 Vendor documents uploaded',
        'group_body': '{business} uploaded {count} documents. Review them.',
    },
    'vendor_product_pending': {
        'title': '📦 Vendor products submitted',
        'body': '{business} submitted {what}: waiting for approval.',
        'type': 'info', 'category': 'vendors', 'priority': 'normal',
        'group': 'vprod:{store_id}',
        'group_title': '📦 Vendor products submitted',
        'group_body': '{business} has {count} product submissions waiting for approval.',
    },
    'vendor_product_changed': {
        'title': '📦 Vendor product changed',
        'body': '{business} changed "{product}": waiting for approval.',
        'type': 'info', 'category': 'vendors', 'priority': 'normal',
        'group': 'vprod:{store_id}',
        'group_title': '📦 Vendor products submitted',
        'group_body': '{business} has {count} product submissions waiting for approval.',
    },
    'dispute_opened': {
        'title': '⚠️ New dispute: order #{order_no}',
        'body': '{reason} - store: {store}.',
        'type': 'warning', 'category': 'disputes', 'priority': 'high',
    },
    'otp_requested': {
        'title': '🔐 OTP requested - {purpose}',
        'body': 'Customer: {customer}. Open OTP management for details.',
        'type': 'info', 'category': 'security', 'priority': 'low',
        'group': 'otp:{purpose}:{customer}',
        'group_title': '🔐 OTP requested - {purpose}',
        'group_body': 'Customer: {customer} requested {count} OTPs. Open OTP management for details.',
    },
    'order_new': {
        'title': '🛒 New order #{order_no}',
        'body': '{store}: {total} ({items} item(s)).',
        'type': 'sale', 'category': 'orders', 'priority': 'normal',
        'group': 'order_new:{store_id}',
        'group_title': '🛒 {count} new orders',
        'group_body': '{store} has {count} new orders waiting.',
    },
    'order_late': {
        'title': '⏰ Late order #{order_no}',
        'body': '{store}: {reason}.',
        'type': 'danger', 'category': 'orders', 'priority': 'critical',
        'group': 'order_late:{order_no}',
    },
    'rider_needed': {
        'title': '🏍️ Rider needed: order #{order_no}',
        'body': '{store}: ready for pickup, no rider assigned yet.',
        'type': 'danger', 'category': 'riders', 'priority': 'critical',
        'group': 'rider_needed:{order_no}',
    },

    # ---------- Orders: vendor / customer / admin ----------
    'order_cancelled_vendor': {
        'title': '❌ Order #{order_no} cancelled',
        'body': '{reason}',
        'type': 'warning', 'category': 'orders', 'priority': 'high',
    },
    'order_missed_vendor': {
        'title': '⏰ Order #{order_no} missed',
        'body': 'You did not respond within {minutes} minutes, so the order was cancelled. Accept or reject new orders faster.',
        'type': 'warning', 'category': 'orders', 'priority': 'high',
    },
    'order_cancelled_customer': {
        'title': '❌ Order #{order_no} cancelled',
        'body': '{store}: {reason}\n{refund_note}',
        'type': 'warning', 'category': 'orders', 'priority': 'high',
    },
    'order_status_customer': {
        'title': '{emoji} Order #{order_no} {status_text}',
        'body': '{store}: {detail}',
        'type': 'info', 'category': 'orders', 'priority': 'normal',
    },
    'rider_assigned_customer': {
        'title': '🏍️ Order #{order_no}: rider assigned',
        'body': 'Rider {rider} ({phone}) is on the way to pick up your order.',
        'type': 'info', 'category': 'orders', 'priority': 'normal',
    },
    'rider_on_way_customer': {
        'title': '🛵 Order #{order_no} is on the way',
        'body': 'Your rider {rider} picked up the order and is heading to you.',
        'type': 'success', 'category': 'orders', 'priority': 'high',
    },
    'refund_due': {
        'title': '💰 Refund due - order #{order_no}',
        'body': '{store}: {reason}. Payment: {method}, {total}.',
        'type': 'warning', 'category': 'payments', 'priority': 'high',
        'group': 'refund:{order_no}',
    },

    # ---------- Escalation: vendor not responding ----------
    'order_unanswered_manager': {
        'title': '⏰ Order #{order_no} still waiting ({minutes} min)',
        'body': '{store}: the vendor has not accepted this order yet. Please check the orders screen now.',
        'type': 'danger', 'category': 'orders', 'priority': 'critical',
        'group': 'unanswered_mgr:{order_no}',
    },
    'order_unanswered_admin': {
        'title': '🚨 Order #{order_no} unanswered for {minutes} min',
        'body': '{store} has not responded. Call the store or reassign / cancel the order.',
        'type': 'danger', 'category': 'orders', 'priority': 'critical',
        'group': 'unanswered_adm:{order_no}',
    },

    # ---------- Vendor alerts ----------
    'vendor_doc_expiring': {
        'title': '📄 {document} expires {when}',
        'body': 'Upload a renewed {document} before {date} to keep your store open.',
        'type': 'warning', 'category': 'vendors', 'priority': 'high',
        'group': 'vdoc_exp:{store_id}:{kind}:{milestone}:{date_key}',
    },
    'vendor_doc_expired': {
        'title': '⛔ {document} has expired',
        'body': 'Your {document} expired on {date}. Upload a new one - your store may be paused until it is approved.',
        'type': 'danger', 'category': 'vendors', 'priority': 'critical',
        'group': 'vdoc_exp:{store_id}:{kind}:x:{date_key}',
    },
    'admin_vendor_doc_expiring': {
        'title': '📄 {business}: {document} expires {when}',
        'body': 'Expiry date {date}. The vendor has been reminded.',
        'type': 'info', 'category': 'vendors', 'priority': 'normal',
    },
    'admin_vendor_doc_expired': {
        'title': '⛔ {business}: {document} expired',
        'body': 'Expired on {date}. Review the store before it keeps taking orders.',
        'type': 'danger', 'category': 'vendors', 'priority': 'high',
    },
    'payout_paid': {
        'title': '💸 Payout sent: {amount}',
        'body': 'Your payout request was paid. Reference: {reference}.',
        'type': 'success', 'category': 'payments', 'priority': 'high',
    },
    'payout_rejected': {
        'title': '❌ Payout request rejected',
        'body': 'Reason: {reason}. You can submit a new request.',
        'type': 'warning', 'category': 'payments', 'priority': 'high',
    },
    'commission_changed': {
        'title': '📊 Your commission changed to {percent}%',
        'body': 'The new rate applies to new orders. Previous rate: {old_percent}%.',
        'type': 'info', 'category': 'payments', 'priority': 'high',
    },
    'store_paused': {
        'title': '⏸️ Your store is paused',
        'body': '{reason}',
        'type': 'warning', 'category': 'vendors', 'priority': 'high',
    },

    # ---------- Rider alerts ----------
    'rider_offer': {
        'title': '🏍️ New order #{order_no}',
        'body': 'Pick up from {store}.',
        'type': 'sale', 'category': 'riders', 'priority': 'critical',
    },
    # Vendor / admin ne order seedha is rider ko de diya (offer nahi, order pehle se rider ka hai)
    'rider_assigned': {
        'title': '📌 Order #{order_no} assigned to you',
        'body': 'Pick up from {store}. This order is already yours.',
        'type': 'sale', 'category': 'riders', 'priority': 'critical',
    },
    'rider_shift_reminder': {
        'title': '🗓️ Your shift starts in {minutes} min',
        'body': '{start}-{end}{zone}. Go online when you are ready.',
        'type': 'info', 'category': 'riders', 'priority': 'high',
        'group': 'shift_rem:{shift_id}',
    },
    'rider_doc_expiring': {
        'title': '📄 {document} expires {when}',
        'body': 'Upload a renewed {document} before {date} or you cannot go online.',
        'type': 'warning', 'category': 'riders', 'priority': 'high',
        'group': 'rdoc_exp:{rider_id}:{kind}:{milestone}:{date_key}',
    },
    'rider_doc_expired': {
        'title': '⛔ {document} has expired',
        'body': 'Expired on {date}. Upload a new one to keep delivering.',
        'type': 'danger', 'category': 'riders', 'priority': 'critical',
        'group': 'rdoc_exp:{rider_id}:{kind}:x:{date_key}',
    },
    'rider_cash_warn': {
        'title': '💵 Cash in hand is near your limit',
        'body': 'You hold {cash} of {limit}. Hand the cash in soon.',
        'type': 'warning', 'category': 'riders', 'priority': 'high',
        'group': 'rider_cash:{rider_id}',
    },
    'rider_cash_over': {
        'title': '🛑 Cash limit reached',
        'body': 'You hold {cash}, over your limit of {limit}. Hand the cash in before taking new orders.',
        'type': 'danger', 'category': 'riders', 'priority': 'critical',
        'group': 'rider_cash:{rider_id}',
    },
    'admin_rider_cash_over': {
        'title': '🛑 Rider {rider} is over the cash limit',
        'body': '{rider} holds {cash} (limit {limit}). Collect the cash.',
        'type': 'danger', 'category': 'riders', 'priority': 'high',
        'group': 'admin_rider_cash:{rider_id}',
    },

    # ---------- Customer alerts ----------
    'wallet_topup_ok': {
        'title': '💳 Payment confirmed',
        'body': '{detail}',
        'type': 'success', 'category': 'payments', 'priority': 'normal',
    },
    'wallet_topup_rejected': {
        'title': '💳 Wallet request not approved',
        'body': '{detail}',
        'type': 'warning', 'category': 'payments', 'priority': 'normal',
    },
    'promo': {
        'title': '🎁 {title}',
        'body': '{body}',
        'type': 'info', 'category': 'marketing', 'priority': 'low',
    },
}


class _Safe(dict):
    """Kami wali ctx key ho to {key} ki jagah khali, error nahi."""
    def __missing__(self, key):
        return ''


def _fmt(text, ctx):
    return (text or '').format_map(_Safe(ctx or {}))


def event_names():
    return sorted(TEMPLATES)


def render_event(event, ctx=None):
    """Event ke template se {title, message, notification_type, category, priority, group_key}. Anjaan event -> KeyError."""
    t = TEMPLATES[event]
    ctx = dict(ctx or {})
    return {
        'title': _fmt(t['title'], ctx)[:200],
        'message': _fmt(t['body'], ctx),
        'notification_type': t.get('type', 'info'),
        'category': t.get('category', 'system'),
        'priority': t.get('priority', 'normal'),
        'group_key': _fmt(t.get('group', ''), ctx)[:80],
    }


def group_text(event, count, ctx=None):
    """Group ban jane par naya (title, message). Template mein group_* na ho to wahi purana text + ' (xN)'."""
    t = TEMPLATES[event]
    ctx = dict(ctx or {}, count=count)
    if t.get('group_title') and t.get('group_body'):
        return _fmt(t['group_title'], ctx)[:200], _fmt(t['group_body'], ctx)
    return (_fmt(t['title'], ctx)[:190] + f' (x{count})')[:200], _fmt(t['body'], ctx)


def group_window_minutes(event):
    return TEMPLATES[event].get('group_window', DEFAULT_GROUP_WINDOW_MIN)


# ---------------------------------------------------------------- snooze
SNOOZE_OPTIONS = {'1h': 60, '3h': 180, 'tomorrow': None, '1w': 7 * 24 * 60}


def snooze_deadline(now, option, tomorrow_at=time(9, 0)):
    """'1h' / '3h' / '1w' (ya sirf minute ka number) / 'tomorrow' (agle din subah 9). Galat option -> None."""
    if option == 'tomorrow':
        return datetime.combine((now + timedelta(days=1)).date(), tomorrow_at, tzinfo=now.tzinfo)
    minutes = SNOOZE_OPTIONS.get(option)
    if minutes is None:
        try:
            minutes = int(option)
        except (TypeError, ValueError):
            return None
    if minutes < 1 or minutes > 60 * 24 * 30:
        return None
    return now + timedelta(minutes=minutes)


# ---------------------------------------------------------------- filters
STATES = ['active', 'archived', 'snoozed']
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def parse_filters(params):
    """Query string (dict jaisa) se saaf filters. Galat values chup-chaap default par."""
    def get(k):
        v = params.get(k, '')
        return (v if isinstance(v, str) else '').strip()
    category = get('category')
    priority = get('priority')
    ntype = get('type')
    state = get('state')
    df, dt = get('date_from'), get('date_to')
    return {
        'category': category if category in CATEGORY_KEYS else 'all',
        'q': get('q')[:80],
        'unread': get('unread') in ('1', 'true', 'on'),
        'priority': priority if priority in PRIORITY_KEYS else '',
        'type': ntype if ntype in TYPE_KEYS else '',
        'state': state if state in STATES else 'active',
        'date_from': df if _DATE_RE.match(df) else '',
        'date_to': dt if _DATE_RE.match(dt) else '',
    }


ACTIONS = {'read', 'unread', 'archive', 'unarchive', 'pin', 'unpin', 'delete', 'snooze', 'unsnooze'}
# Ye actions sirf apni (user=request.user) notifications par; user=None wali sab ki shared hoti hain
OWN_ONLY_ACTIONS = {'archive', 'unarchive', 'pin', 'unpin', 'delete', 'snooze', 'unsnooze'}
MAX_BULK = 200


def clean_ids(raw):
    """Bulk ke liye ids: sirf positive int, duplicate hatao, MAX_BULK tak."""
    out, seen = [], set()
    for x in raw or []:
        try:
            i = int(x)
        except (TypeError, ValueError):
            continue
        if i > 0 and i not in seen:
            seen.add(i)
            out.append(i)
        if len(out) >= MAX_BULK:
            break
    return out
