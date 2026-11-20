from types import SimpleNamespace

from django.test import SimpleTestCase

from app.customer import pickup_code
from app.utils import marketplace_alert_rules as ar
from app.utils.notification_rules import render_event


class PickupNoShowRulesTests(SimpleTestCase):
    def test_stages_follow_minutes(self):
        self.assertIsNone(ar.pickup_noshow_stage(None))
        self.assertIsNone(ar.pickup_noshow_stage(0))
        self.assertIsNone(ar.pickup_noshow_stage(ar.PICKUP_REMIND_MIN - 1))
        self.assertEqual(ar.pickup_noshow_stage(ar.PICKUP_REMIND_MIN), 'customer')
        self.assertEqual(ar.pickup_noshow_stage(ar.PICKUP_VENDOR_MIN), 'vendor')
        self.assertEqual(ar.pickup_noshow_stage(ar.PICKUP_ADMIN_MIN), 'admin')
        self.assertEqual(ar.pickup_noshow_stage(10_000), 'admin')

    def test_order_of_thresholds(self):
        self.assertLess(ar.PICKUP_REMIND_MIN, ar.PICKUP_VENDOR_MIN)
        self.assertLess(ar.PICKUP_VENDOR_MIN, ar.PICKUP_ADMIN_MIN)


class PickupCodeAndEventTests(SimpleTestCase):
    def _order(self, pk=11, no='SO-11'):
        return SimpleNamespace(pk=pk, order_no=no)

    def test_customer_code_is_stable_4_digits_and_not_rider_code(self):
        o = self._order()
        c = pickup_code.customer_code_for(o)
        self.assertRegex(c, r'^\d{4}$')
        self.assertEqual(c, pickup_code.customer_code_for(self._order()))
        # rider wale code se alag (kam az kam kisi order par farq aata hai)
        self.assertTrue(any(pickup_code.customer_code_for(self._order(i, f'SO-{i}')) !=
                            pickup_code.code_for(self._order(i, f'SO-{i}')) for i in range(1, 30)))

    def test_events_render(self):
        ctx = {'order_no': 'SO-1', 'store': 'Pizza Hub', 'minutes': 95, 'code': '1234'}
        for ev in ('pickup_reminder_customer', 'pickup_not_collected_vendor', 'pickup_not_collected_admin'):
            r = render_event(ev, ctx)
            self.assertIn('SO-1', r['title'])
            self.assertTrue(r['group_key'])
