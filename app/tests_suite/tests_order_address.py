"""Order ka address: order ke waqt copy hota hai, sirf pending order mein badal sakta hai."""
from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase

from app.models import SaleOrder

ROOT = Path(__file__).resolve().parents[2]


def _o(status='pending', own='', cust='Customer Addr'):
    return SimpleNamespace(status=status, delivery_address=own, customer=SimpleNamespace(address=cust))


class OrderAddressModelTests(SimpleTestCase):
    def test_ship_address_prefers_order_copy(self):
        self.assertEqual(SaleOrder.ship_address(_o(own='  Order Addr ')), 'Order Addr')

    def test_old_orders_fall_back_to_customer_address(self):
        self.assertEqual(SaleOrder.ship_address(_o(own='')), 'Customer Addr')

    def test_no_address_anywhere_is_empty(self):
        self.assertEqual(SaleOrder.ship_address(_o(own='', cust=None)), '')

    def test_only_pending_can_change(self):
        self.assertTrue(SaleOrder.can_change_address(_o('pending')))
        for st in ('confirmed', 'processing', 'ready', 'delivered', 'cancelled'):
            self.assertFalse(SaleOrder.can_change_address(_o(st)), st)


class OrderAddressWiringTests(SimpleTestCase):
    def _read(self, rel):
        return (ROOT / rel).read_text(encoding='utf-8')

    def test_place_order_saves_address_on_order(self):
        self.assertIn('delivery_address=', self._read('app/customer/views_customer_portal.py'))

    def test_change_view_url_exists(self):
        self.assertIn('change_order_address', self._read('app/urls.py'))

    def test_rider_vendor_and_pos_use_order_address(self):
        for rel in ('app/customer/views_rider_portal.py', 'app/customer/batch_nav.py', 'app/customer/pos_api.py'):
            self.assertIn('ship_address()', self._read(rel), rel)
        self.assertIn('o.ship_address', self._read('templates/customer_portal/vendor/orders.html'))

    def test_rider_does_not_read_profile_address_any_more(self):
        self.assertNotIn("getattr(cust, 'address'", self._read('app/customer/views_rider_portal.py'))

    def test_customer_page_shows_change_form_only_when_allowed(self):
        t = self._read('templates/customer_portal/order_detail.html')
        self.assertIn('order.can_change_address', t)
        self.assertIn("change_order_address", t)


from decimal import Decimal as D

from app.customer import address_change as ac


class AddressChangeFeeTests(SimpleTestCase):
    AREAS = [('Raiwind', D('100')), ('DHA', D('50'))]

    def test_area_extra_found_in_text(self):
        self.assertEqual(ac.area_extra_for_text('House 5, Raiwind road', self.AREAS), (D('100'), 'Raiwind'))
        self.assertEqual(ac.area_extra_for_text('House 5, Gulberg', self.AREAS), (D('0'), ''))

    def test_fee_goes_up_for_far_area(self):
        self.assertEqual(ac.new_delivery_fee(D('150'), D('0'), D('100')), D('250'))

    def test_fee_goes_down_when_back_to_near_area(self):
        self.assertEqual(ac.new_delivery_fee(D('250'), D('100'), D('0')), D('150'))

    def test_never_below_zero(self):
        self.assertEqual(ac.new_delivery_fee(D('50'), D('100'), D('0')), D('0'))

    def test_free_or_waived_delivery_not_touched(self):
        self.assertEqual(ac.new_delivery_fee(D('0'), D('0'), D('100')), D('0'))
        self.assertEqual(ac.new_delivery_fee(D('150'), D('0'), D('100'), waived=D('150')), D('150'))

    def test_note_line_mentions_fee_only_when_changed(self):
        self.assertIn('Delivery fee', ac.note_line('a', 'b', D('100'), D('200'), 'now'))
        self.assertNotIn('Delivery fee', ac.note_line('a', 'b', D('100'), D('100'), 'now'))
        self.assertIn(ac.NOTE_TAG, ac.note_line('a', 'b', D('1'), D('1'), 'now'))

    def test_view_and_vendor_page_wired(self):
        root = Path(__file__).resolve().parents[2]
        self.assertIn('address_change.fee_for_change', (root / 'app/customer/views_customer_portal.py').read_text(encoding='utf-8'))
        self.assertIn('ADDRESS CHANGED', (root / 'templates/customer_portal/vendor/orders.html').read_text(encoding='utf-8'))


class AddressChangePinTests(SimpleTestCase):
    def _read(self, rel):
        return (Path(__file__).resolve().parents[2] / rel).read_text(encoding='utf-8')

    def test_view_reads_pin_and_uses_distance_plan(self):
        t = self._read('app/customer/views_customer_portal.py')
        self.assertIn('address_change.distance_plan', t)
        self.assertIn("parse_coords(request.POST.get('lat')", t)

    def test_order_page_has_pin_button_and_hidden_coords(self):
        t = self._read('templates/customer_portal/order_detail.html')
        for needle in ('newShipPinBtn', 'name="lat"', 'name="lng"'):
            self.assertIn(needle, t)

    def test_distance_fee_uses_same_formula_as_checkout(self):
        from app.customer.delivery_pricing import compute_fee
        # base 100, Rs 20/km, 2 km free, 5 km door, area extra 50 -> 100 + 20*3 + 50
        self.assertEqual(compute_fee(D('100'), D('20'), D('2'), 5, D('50')), D('210'))
