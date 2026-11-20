"""Pure tests (no Django):  python tests/test_marketplace_alert_rules_pure.py"""
import importlib.util
import os
from datetime import date

_p = os.path.join(os.path.dirname(__file__), '..', 'app', 'utils', 'marketplace_alert_rules.py')
_s = importlib.util.spec_from_file_location('marketplace_alert_rules', _p)
m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(m)

_p2 = os.path.join(os.path.dirname(__file__), '..', 'app', 'utils', 'notification_rules.py')
_s2 = importlib.util.spec_from_file_location('notification_rules', _p2)
n = importlib.util.module_from_spec(_s2)
_s2.loader.exec_module(n)


def test_escalation_default_5_10():
    assert m.escalation_stage(4) is None
    assert m.escalation_stage(5) == 'manager'
    assert m.escalation_stage(9.9) == 'manager'
    assert m.escalation_stage(10) == 'admin'
    assert m.escalation_stage(None) is None


def test_escalation_clamped_by_auto_expire():
    assert m.escalation_levels(5) == (3, 4)           # order 5 min par cancel hota hai
    assert m.escalation_levels(15) == (5, 10)          # lamba timeout: asal 5/10
    assert m.escalation_levels(0) == (5, 10)           # auto-expire band
    assert m.escalation_levels(2) == (1, 2)
    assert m.escalation_stage(3, expire_min=5) == 'manager'
    assert m.escalation_stage(4, expire_min=5) == 'admin'


def test_expiry_milestones():
    t = date(2026, 11, 14)
    assert m.expiry_milestone(None, t) is None
    assert m.expiry_milestone(date(2026, 11, 13), t) == 'expired'
    assert m.expiry_milestone(t, t) == 0
    assert m.expiry_milestone(date(2026, 11, 19), t) == 7
    assert m.expiry_milestone(date(2026, 11, 21), t) == 7
    assert m.expiry_milestone(date(2026, 11, 22), t) == 30
    assert m.expiry_milestone(date(2026, 12, 14), t) == 30
    assert m.expiry_milestone(date(2026, 12, 15), t) is None
    assert m.expiry_when(0) == 'today' and m.expiry_when(7) == 'in 7 days'


def test_shift_reminder():
    assert m.shift_reminder_due(30) and m.shift_reminder_due(1)
    assert not m.shift_reminder_due(0) and not m.shift_reminder_due(31) and not m.shift_reminder_due(None)


def test_new_templates_render():
    for ev in ('order_unanswered_manager', 'vendor_doc_expiring', 'rider_cash_over', 'payout_paid', 'commission_changed'):
        r = n.render_event(ev, {'order_no': 'X1', 'document': 'CR', 'when': 'today', 'store_id': 3, 'kind': 'cr',
                                'milestone': 0, 'date_key': '261114', 'rider_id': 9})
        assert r['title'] and len(r['group_key']) <= 80
    assert '{' not in n.render_event('vendor_doc_expiring', {'document': 'CR', 'when': 'today'})['title']


if __name__ == '__main__':
    for k, v in list(globals().items()):
        if k.startswith('test_'):
            v()
    print('ok')
