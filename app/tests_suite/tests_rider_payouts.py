from decimal import Decimal

from django.test import SimpleTestCase

from app.customer import rider_payouts as p

D = Decimal


class PayoutMathTests(SimpleTestCase):
    def test_available_subtracts_cash_and_pending(self):
        self.assertEqual(p.available_amount(D('100'), D('30'), D('20')), D('50.00'))

    def test_available_never_negative(self):
        self.assertEqual(p.available_amount(D('10'), D('30'), D('0')), D('0.00'))
        self.assertEqual(p.available_amount(None, None, None), D('0.00'))

    def test_parse_amount(self):
        self.assertEqual(p.parse_amount('1,250.5'), D('1250.50'))
        for bad in ('', 'abc', '0', '-3', 'NaN', 'Infinity'):
            with self.assertRaises(p.PayoutError):
                p.parse_amount(bad)
