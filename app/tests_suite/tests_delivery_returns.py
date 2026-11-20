from datetime import datetime, timedelta
from decimal import Decimal

from django.test import SimpleTestCase

from app.customer import delivery_returns as r

T0 = datetime(2026, 11, 16, 12, 0, 0)


class WaitTests(SimpleTestCase):
    def test_wait_counts_down(self):
        self.assertEqual(r.wait_seconds_left(T0, 10, 'unreachable', T0), 600)
        self.assertEqual(r.wait_seconds_left(T0, 10, 'unreachable', T0 + timedelta(minutes=4)), 360)

    def test_wait_over(self):
        self.assertEqual(r.wait_seconds_left(T0, 10, 'wrong_address', T0 + timedelta(minutes=11)), 0)

    def test_refused_and_zero_wait_skip_wait(self):
        self.assertEqual(r.wait_seconds_left(T0, 10, 'refused', T0), 0)
        self.assertEqual(r.wait_seconds_left(T0, 0, 'unreachable', T0), 0)


class FeeTests(SimpleTestCase):
    def test_fee_percent(self):
        self.assertEqual(r.fee_for(Decimal('50'), Decimal('100')), Decimal('50.00'))
        self.assertEqual(r.fee_for(Decimal('50'), Decimal('50')), Decimal('25.00'))
        self.assertEqual(r.fee_for(Decimal('50'), Decimal('0')), Decimal('0.00'))

    def test_fee_percent_is_clamped(self):
        self.assertEqual(r.fee_for(Decimal('50'), Decimal('250')), Decimal('50.00'))
        self.assertEqual(r.fee_for(Decimal('50'), Decimal('-5')), Decimal('0.00'))
