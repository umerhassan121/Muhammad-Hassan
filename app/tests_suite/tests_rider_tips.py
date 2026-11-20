from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase

from app.customer import rider_tips as t


class TipAmountTests(SimpleTestCase):
    def test_valid_amounts(self):
        with mock.patch.object(t, 'max_tip', return_value=Decimal('1000')):
            self.assertEqual(t.validate_amount('50'), Decimal('50.00'))
            self.assertEqual(t.validate_amount('1,000'), Decimal('1000.00'))

    def test_invalid_amounts(self):
        with mock.patch.object(t, 'max_tip', return_value=Decimal('1000')):
            for bad in ('', 'abc', '0', '-5', '1000.01'):
                with self.assertRaises(t.TipError):
                    t.validate_amount(bad)

    def test_presets_within_default_max(self):
        self.assertTrue(all(p <= t.DEFAULT_MAX for p in t.PRESETS))
