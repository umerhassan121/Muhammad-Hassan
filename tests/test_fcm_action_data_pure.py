"""APK ke Accept/Decline buttons: data-only FCM message (pure Python; firebase/Django ki zaroorat nahi)."""
import json
import pathlib

_SRC = (pathlib.Path(__file__).resolve().parents[1] / 'app' / 'utils' / 'push_service.py').read_text()
_FN = _SRC[_SRC.index('def fcm_action_data'):_SRC.index('def fcm_message_parts')]
_NS = {}
exec(_FN, _NS)
fcm_action_data = _NS['fcm_action_data']

_PROF = {'kind': 'rider', 'urgent': True, 'tag': 'rider-order-5', 'actions': [
    {'action': 'accept', 'title': 'Accept', 'token': 'tok-a'},
    {'action': 'decline', 'title': 'Decline', 'token': 'tok-d'},
    {'action': 'extra', 'title': 'Third', 'token': 'tok-x'},
]}


def test_action_data_is_all_strings_and_has_two_buttons():
    d = fcm_action_data('New order #5', 'Pick up from Store', '/shop/rider/', _PROF)
    assert d['act'] == '1' and d['kind'] == 'rider' and d['tag'] == 'rider-order-5'
    assert all(isinstance(v, str) for v in d.values())        # FCM data: sirf string
    acts = json.loads(d['actions'])
    assert [a['action'] for a in acts] == ['accept', 'decline']
    assert acts[0]['token'] == 'tok-a' and acts[1]['title'] == 'Decline'


def test_buttons_without_token_are_dropped_and_text_trimmed():
    prof = dict(_PROF, actions=[{'action': 'open', 'title': 'Open', 'url': '/shop/rider/'}])
    d = fcm_action_data('T' * 500, 'B' * 900, None, prof)
    assert json.loads(d['actions']) == []
    assert len(d['title']) == 120 and len(d['body']) == 300 and d['url'] == '/shop/rider/'


# ---- Vendor APK: Accept / Reject buttons + Rider/Vendor app-wise device filter ----------------------------
_FN2 = _SRC[_SRC.index('def devices_for_kind'):_SRC.index('def _deliver_fcm')]
_NS2 = {}
exec(_FN2, _NS2)
devices_for_kind = _NS2['devices_for_kind']

_VPROF = {'kind': 'vendor', 'urgent': True, 'tag': 'vendor-order-9', 'actions': [
    {'action': 'accept', 'title': 'Accept', 'token': 'tok-a'},
    {'action': 'reject', 'title': 'Reject', 'token': 'tok-r'},
]}


def test_vendor_action_data_has_accept_reject_and_vendor_default_url():
    d = fcm_action_data('New order #9', 'A customer ordered', None, _VPROF)
    assert d['act'] == '1' and d['kind'] == 'vendor' and d['tag'] == 'vendor-order-9'
    assert d['url'] == '/shop/vendor/orders/'                  # vendor ko tap par orders page
    assert all(isinstance(v, str) for v in d.values())
    acts = json.loads(d['actions'])
    assert [a['action'] for a in acts] == ['accept', 'reject']
    assert acts[1]['title'] == 'Reject' and acts[1]['token'] == 'tok-r'


def test_rider_default_url_unchanged():
    d = fcm_action_data('New order #5', 'x', None, _PROF)
    assert d['url'] == '/shop/rider/'


def test_vendor_push_goes_only_to_vendor_and_other_apps():
    devs = [{'id': 1, 'app': 'rider'}, {'id': 2, 'app': 'vendor'}, {'id': 3, 'app': 'admin'}, {'id': 4}]
    assert [d['id'] for d in devices_for_kind('vendor', devs)] == [2, 3, 4]


def test_rider_push_skips_vendor_app_and_other_kinds_get_everything():
    devs = [{'id': 1, 'app': 'rider'}, {'id': 2, 'app': 'vendor'}, {'id': 3, 'app': 'admin'}]
    assert [d['id'] for d in devices_for_kind('rider', devs)] == [1, 3]
    assert [d['id'] for d in devices_for_kind('order', devs)] == [1, 2, 3]
    assert [d['id'] for d in devices_for_kind('admin', devs)] == [1, 2, 3]


def test_customer_app_gets_only_order_push_and_order_push_skips_rider_vendor_when_customer_app_exists():
    devs = [{'id': 1, 'app': 'rider'}, {'id': 2, 'app': 'vendor'}, {'id': 3, 'app': 'customer'}]
    assert [d['id'] for d in devices_for_kind('order', devs)] == [3]
    assert [d['id'] for d in devices_for_kind('vendor', devs)] == [2]
    assert [d['id'] for d in devices_for_kind('rider', devs)] == [1]
    assert [d['id'] for d in devices_for_kind('admin', devs)] == [1, 2]
    assert [d['id'] for d in devices_for_kind('order', devs[:2])] == [1, 2]    # customer app nahi: pehle jaisa
