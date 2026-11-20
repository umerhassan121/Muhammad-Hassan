"""
Tests: ESC/POS receipt bytes (app/customer/escpos.py). Pure Python - no database.

Run:  python manage.py test app.tests_suite.tests_escpos -v 2
"""
from django.test import SimpleTestCase

from app.customer import escpos

PAYLOAD = {
    'order_no': 'ORD-1', 'prep_minutes': 20, 'scheduled_for': None, 'payment_method': 'cod',
    'customer': {'name': 'Ali', 'phone': '0300', 'address': 'House 5'},
    'items': [{'qty': 2.0, 'name': 'Chicken Biryani Special Large Portion', 'unit_price': '450.00',
               'options': 'Extra raita', 'note': 'no onion'}],
    'subtotal': '900', 'delivery_fee': '50', 'total': '950', 'cash_due': '950',
}


class EscposTests(SimpleTestCase):
    def test_columns(self):
        self.assertEqual(escpos.columns(58), 32)
        self.assertEqual(escpos.columns(80), 48)

    def test_clean_text(self):
        self.assertEqual(escpos.clean('Caf\u00e9'), 'Cafe')
        self.assertEqual(escpos.clean('a\nb\tc'), 'a b c')
        self.assertEqual(escpos.clean('\u0627\u0631\u062f\u0648'), '????')      # Urdu -> placeholders

    def test_two_col_fits_width(self):
        for line in escpos.two_col('x' * 80, '123.00', 32):
            self.assertLessEqual(len(line), 32)
        self.assertTrue(escpos.two_col('Tea', '10.00', 32)[0].endswith('10.00'))

    def test_receipt_starts_with_init_and_ends_with_cut(self):
        for width in (58, 80):
            data = escpos.build_receipt(PAYLOAD, 'Test Store', width)
            self.assertTrue(data.startswith(escpos.INIT))
            self.assertTrue(data.endswith(escpos.CUT))

    def test_receipt_contains_key_lines(self):
        text = escpos.build_receipt(PAYLOAD, 'Test Store', 58).decode('cp437')
        for needle in ('Test Store', '#ORD-1', 'Tel: 0300', 'NOTE: no onion', 'TOTAL', '950.00', 'Cash to collect'):
            self.assertIn(needle, text)

    def test_prepaid_has_no_cash_to_collect(self):
        text = escpos.build_receipt(dict(PAYLOAD, payment_method='wallet'), 'S', 58).decode('cp437')
        self.assertNotIn('Cash to collect', text)
