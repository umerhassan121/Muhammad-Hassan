"""Pure tests (no Django):  python tests/test_notification_rules_pure.py"""
import importlib.util
import os
from datetime import datetime, timedelta, timezone

_p = os.path.join(os.path.dirname(__file__), '..', 'app', 'utils', 'notification_rules.py')
_s = importlib.util.spec_from_file_location('notification_rules', _p)
n = importlib.util.module_from_spec(_s)
_s.loader.exec_module(n)

NOW = datetime(2026, 11, 14, 13, 0, tzinfo=timezone.utc)


def test_all_templates_valid():
    for ev, t in n.TEMPLATES.items():
        assert t['priority'] in n.PRIORITY_KEYS, ev
        assert t['category'] in n.CATEGORY_KEYS, ev
        assert t['type'] in n.TYPE_KEYS, ev
        r = n.render_event(ev, {})                 # kami wali ctx se bhi na tootay
        assert r['title'] and r['message'] is not None
        if t.get('group_title'):
            assert t.get('group_body') and t.get('group'), ev


def test_render_event():
    r = n.render_event('vendor_registered', {'business': 'Shop5', 'city': 'Khanewal', 'owner': 'Ali', 'status': 'waiting for approval'})
    assert r['title'] == '🏢 New vendor registered'
    assert r['message'] == 'Shop5 (Khanewal), Ali: waiting for approval.'
    assert r['priority'] == 'high' and r['category'] == 'vendors' and r['group_key'] == ''


def test_missing_ctx_is_blank_not_error():
    r = n.render_event('dispute_opened', {'order_no': 'A1'})
    assert r['title'] == '⚠️ New dispute: order #A1' and r['message'] == ' - store: .'


def test_unknown_event():
    try:
        n.render_event('nope')
        assert False
    except KeyError:
        pass


def test_braces_in_user_data_are_safe():
    r = n.render_event('vendor_docs_uploaded', {'business': '{evil}', 'document': 'CR', 'store_id': 4})
    assert '{evil}' in r['message'] and r['group_key'] == 'vdocs:4'


def test_group_text():
    t, m = n.group_text('order_new', 5, {'store': 'Pizza Hut', 'store_id': 1})
    assert t == '🛒 5 new orders' and m == 'Pizza Hut has 5 new orders waiting.'
    t, m = n.group_text('order_late', 3, {'order_no': 'B7', 'store': 'X', 'reason': 'slow'})
    assert t.endswith('(x3)') and len(t) <= 200


def test_group_keys_differ_per_store():
    a = n.render_event('order_new', {'store_id': 1})['group_key']
    b = n.render_event('order_new', {'store_id': 2})['group_key']
    assert a != b and a and b


def test_vendor_product_events_share_group():
    a = n.render_event('vendor_product_pending', {'store_id': 9, 'business': 'S', 'what': '3 products'})
    b = n.render_event('vendor_product_changed', {'store_id': 9, 'business': 'S', 'product': 'Tea'})
    assert a['group_key'] == b['group_key'] == 'vprod:9'
    assert a['message'] == 'S submitted 3 products: waiting for approval.'
    assert b['message'] == 'S changed "Tea": waiting for approval.'
    t, m = n.group_text('vendor_product_changed', 4, {'business': 'S', 'store_id': 9})
    assert m == 'S has 4 product submissions waiting for approval.'


def test_snooze_deadline():
    assert n.snooze_deadline(NOW, '1h') == NOW + timedelta(hours=1)
    assert n.snooze_deadline(NOW, '3h') == NOW + timedelta(hours=3)
    assert n.snooze_deadline(NOW, '1w') == NOW + timedelta(days=7)
    assert n.snooze_deadline(NOW, '45') == NOW + timedelta(minutes=45)
    tm = n.snooze_deadline(NOW, 'tomorrow')
    assert tm == datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)
    for bad in ('', 'abc', '0', '-5', '999999', None):
        assert n.snooze_deadline(NOW, bad) is None, bad


def test_parse_filters_defaults_and_cleaning():
    f = n.parse_filters({})
    assert f == {'category': 'all', 'q': '', 'unread': False, 'priority': '', 'type': '',
                 'state': 'active', 'date_from': '', 'date_to': ''}
    f = n.parse_filters({'category': 'orders', 'q': '  shop5  ', 'unread': '1', 'priority': 'critical',
                         'type': 'danger', 'state': 'archived', 'date_from': '2026-11-01', 'date_to': '2026-11-14'})
    assert f['category'] == 'orders' and f['q'] == 'shop5' and f['unread'] and f['state'] == 'archived'
    bad = n.parse_filters({'category': 'hack', 'priority': 'x', 'type': 'y', 'state': 'z',
                           'date_from': '1/2/3', 'date_to': "2026-11-1'; DROP"})
    assert bad['category'] == 'all' and bad['priority'] == '' and bad['type'] == '' and bad['state'] == 'active'
    assert bad['date_from'] == '' and bad['date_to'] == ''
    assert len(n.parse_filters({'q': 'x' * 500})['q']) == 80


def test_clean_ids():
    assert n.clean_ids(['3', 3, '5', 'x', None, -1, 0, '7']) == [3, 5, 7]
    assert len(n.clean_ids(list(range(1, 1000)))) == n.MAX_BULK
    assert n.clean_ids(None) == []


def test_actions():
    assert 'read' not in n.OWN_ONLY_ACTIONS and 'delete' in n.OWN_ONLY_ACTIONS
    assert n.OWN_ONLY_ACTIONS <= n.ACTIONS


if __name__ == '__main__':
    k = 0
    for name, f in list(globals().items()):
        if name.startswith('test_'):
            f(); k += 1
    print(f'{k} tests OK')
