from types import SimpleNamespace

from django.core.cache import cache
from django.test import SimpleTestCase

from app.customer import delivery_otp as d


def _order(pk=7, no='SO-7'):
    return SimpleNamespace(pk=pk, order_no=no)


class DeliveryOtpTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_code_is_stable_4_digits_and_differs_per_order(self):
        a = d.code_for(_order())
        self.assertEqual(a, d.code_for(_order()))
        self.assertRegex(a, r'^\d{4}$')
        self.assertTrue(any(d.code_for(_order(i, f'SO-{i}')) != a for i in range(8, 20)))

    def test_right_code_passes(self):
        o = _order()
        self.assertEqual(d.check(o, d.code_for(o)), (True, ''))

    def test_empty_and_wrong_fail(self):
        o = _order()
        self.assertFalse(d.check(o, '')[0])
        wrong = '0000' if d.code_for(o) != '0000' else '1111'
        self.assertFalse(d.check(o, wrong)[0])

    def test_lock_after_max_wrong_even_for_right_code(self):
        o = _order()
        wrong = '0000' if d.code_for(o) != '0000' else '1111'
        for _ in range(d.MAX_WRONG):
            d.check(o, wrong)
        self.assertTrue(d.is_locked(o.pk))
        self.assertFalse(d.check(o, d.code_for(o))[0])

    def test_right_code_resets_counter(self):
        o = _order()
        wrong = '0000' if d.code_for(o) != '0000' else '1111'
        d.check(o, wrong)
        d.check(o, d.code_for(o))
        self.assertFalse(d.is_locked(o.pk))
