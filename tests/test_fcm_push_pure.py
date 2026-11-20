"""FCM (native app) push: message ke hisse (pure Python; firebase/Django ki zaroorat nahi)."""
import pathlib

_SRC = (pathlib.Path(__file__).resolve().parents[1] / 'app' / 'utils' / 'push_service.py').read_text()
_FN = _SRC[_SRC.index('def fcm_message_parts'):_SRC.index('def _deliver_fcm')]
_NS = {}
exec(_FN, _NS)
fcm_message_parts = _NS['fcm_message_parts']


def test_urgent_order_uses_orders_channel_high_priority():
    prof = {'urgent': True, 'kind': 'rider', 'tag': 'rider-order-5'}
    n, d, a = fcm_message_parts('Naya order', 'Store se pickup', '/shop/rider/', prof)
    assert a['channel_id'] == 'orders_v2' and a['priority'] == 'high' and a['ttl_seconds'] == 600
    assert a['tag'] == 'rider-order-5'
    assert d['url'] == '/shop/rider/' and d['kind'] == 'rider'
    assert n == {'title': 'Naya order', 'body': 'Store se pickup'}


def test_normal_message_uses_general_channel():
    prof = {'urgent': False, 'kind': 'rider', 'tag': '/shop/rider/earnings/'}
    n, d, a = fcm_message_parts('Kamai', None, '/shop/rider/earnings/', prof)
    assert a['channel_id'] == 'general' and a['priority'] == 'normal' and a['ttl_seconds'] == 3600
    assert n['body'] == ''


def test_long_text_is_trimmed():
    prof = {'urgent': False, 'kind': 'rider', 'tag': 't'}
    n, d, a = fcm_message_parts('T' * 500, 'B' * 900, '/shop/' + 'x' * 500, prof)
    assert len(n['title']) == 120 and len(n['body']) == 300 and len(d['url']) == 300
