"""
Tests: Mart home + substitution.

Run:  python manage.py test app.tests_suite.tests_mart -v 2

NOTE: written by reading the code, without a Django project to run it in. If a fixture line fails on
a field name, fix it in setUp - the assertions are what matter.
"""
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from app.customer import substitution
from app.tests_suite.tests_dark_store import make_profile


class SubstitutionUnitTests(SimpleTestCase):
    def test_clean_falls_back_to_default(self):
        self.assertEqual(substitution.clean('call'), 'call')
        self.assertEqual(substitution.clean(' REMOVE '), 'remove')
        self.assertEqual(substitution.clean('junk'), substitution.DEFAULT)
        self.assertEqual(substitution.clean(None), substitution.DEFAULT)

    def test_current_reads_session(self):
        self.assertEqual(substitution.current({}), 'best')
        self.assertEqual(substitution.current({substitution.SESSION_KEY: 'call'}), 'call')


class MartViewTests(TestCase):
    def test_no_mart_shows_message_not_error(self):
        r = self.client.get(reverse('mart_home'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Mart is not available')

    def test_substitution_saved_in_session(self):
        r = self.client.post(reverse('mart_substitution'), data='{"pref": "call"}', content_type='application/json')
        self.assertEqual(r.json(), {'success': True, 'pref': 'call'})
        self.assertEqual(self.client.session[substitution.SESSION_KEY], 'call')

    def test_substitution_rejects_get(self):
        self.assertEqual(self.client.get(reverse('mart_substitution')).status_code, 405)

    def test_note_line_only_for_mart_cart(self):
        mart = make_profile(name='Mart A', phone='03001110010', is_dark_store=True)
        plain = make_profile(name='Cafe', phone='03001110011')
        s = {substitution.SESSION_KEY: 'call'}
        self.assertIn('Call me first', substitution.note_line(s, {'1': {'vendor_id': mart.vendor_id}}))
        self.assertEqual(substitution.note_line(s, {'1': {'vendor_id': plain.vendor_id}}), '')
        self.assertEqual(substitution.note_line(s, {}), '')


class OrderItemChangeGuardTests(SimpleTestCase):
    """Replace / remove ke pehle ke pehre (DB ke bina)."""

    def _order(self, status, vendor_id=1):
        from types import SimpleNamespace
        return SimpleNamespace(status=status, vendor_id=vendor_id)

    def test_other_vendors_order_is_refused(self):
        from types import SimpleNamespace
        from app.customer import order_item_changes as oic
        with self.assertRaises(oic.OrderChangeError):
            oic._check(self._order('pending', vendor_id=2), SimpleNamespace(id=1))

    def test_ready_or_later_order_is_refused(self):
        from types import SimpleNamespace
        from app.customer import order_item_changes as oic
        for status in ('ready', 'delivered', 'cancelled'):
            with self.assertRaises(oic.OrderChangeError):
                oic._check(self._order(status), SimpleNamespace(id=1))

    def test_editable_order_passes(self):
        from types import SimpleNamespace
        from app.customer import order_item_changes as oic
        for status in ('pending', 'confirmed', 'processing'):
            oic._check(self._order(status), SimpleNamespace(id=1))


class GstMathTests(SimpleTestCase):
    """GST (tax-inclusive) ka hisaab - DB ke bina."""

    def test_included_part_of_inclusive_price(self):
        from decimal import Decimal
        from app.customer import tax
        self.assertEqual(tax.included(Decimal('118'), Decimal('18')), Decimal('18.00'))
        self.assertEqual(tax.included(Decimal('100'), Decimal('0')), Decimal('0.00'))
        self.assertEqual(tax.included(Decimal('0'), Decimal('18')), Decimal('0.00'))

    def test_discount_reduces_tax_proportionally(self):
        from decimal import Decimal
        from app.customer import tax
        self.assertEqual(tax._after_discount(Decimal('18.00'), Decimal('118'), Decimal('59')), Decimal('9.00'))
        self.assertEqual(tax._after_discount(Decimal('18.00'), Decimal('118'), 0), Decimal('18.00'))

    def test_product_rate_overrides_default(self):
        from decimal import Decimal
        from types import SimpleNamespace
        from app.customer import tax
        cfg = {'rate': Decimal('18')}
        self.assertEqual(tax.rate_for(SimpleNamespace(gst_rate=None), cfg), Decimal('18'))
        self.assertEqual(tax.rate_for(SimpleNamespace(gst_rate=Decimal('0')), cfg), Decimal('0'))
        self.assertEqual(tax.rate_for(SimpleNamespace(gst_rate=Decimal('5')), cfg), Decimal('5'))
