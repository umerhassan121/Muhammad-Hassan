from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase

from app.customer import delivery_eta as eta


class PureTests(SimpleTestCase):
    def test_fallback_leg_uses_road_factor_and_speed(self):
        sec, meters = eta.fallback_leg((26.2, 50.5), (26.2, 50.5))
        self.assertEqual((sec, meters), (0, 0))
        sec, meters = eta.fallback_leg((26.20, 50.5), (26.209, 50.5))     # ~1 km seedhi
        self.assertAlmostEqual(meters, 1000 * eta.ROAD_FACTOR, delta=15)
        self.assertAlmostEqual(sec, meters / (eta.FALLBACK_SPEED_KMH / 3.6), delta=1)

    def test_minutes_round_up_and_minimum_one(self):
        self.assertEqual(eta.build(0, 500, 'delivery', False)['minutes'], 1)
        self.assertEqual(eta.build(61, 500, 'delivery', False)['minutes'], 2)
        self.assertEqual(eta.build(-5, 500, 'delivery', False)['minutes'], 1)

    def test_clock_text(self):
        r = eta.build(12 * 60, 3000, 'delivery', False, now=datetime(2026, 11, 16, 18, 30))
        self.assertEqual(r['clock'], '6:42 PM')
        r = eta.build(5 * 60, 3000, 'delivery', False, now=datetime(2026, 11, 16, 9, 0))
        self.assertEqual(r['clock'], '9:05 AM')

    def test_arriving_only_for_delivery_stage_and_close(self):
        self.assertTrue(eta.build(30, 80, 'delivery', False)['arriving'])
        self.assertFalse(eta.build(30, 500, 'delivery', False)['arriving'])
        self.assertFalse(eta.build(30, 80, 'pickup', False)['arriving'])


class ForDeliveryTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def _objs(self, status='assigned', drop=True, rider_loc=True):
        di = SimpleNamespace(status=status)
        order = SimpleNamespace(pk=7, delivery_lat=26.2 if drop else None, delivery_lng=50.5 if drop else None)
        rider = SimpleNamespace(last_lat=26.21 if rider_loc else None, last_lng=50.51 if rider_loc else None)
        return di, order, rider

    def test_pickup_stage_adds_both_legs_and_buffer(self):
        di, order, rider = self._objs('assigned')
        with mock.patch.object(eta, '_leg', side_effect=[(300, 2000, False), (600, 3000, False)]), \
                mock.patch('app.customer.dispatch._store_coords', return_value=(26.22, 50.52)):
            r = eta.for_delivery(di, order, rider)
        self.assertEqual(r['stage'], 'pickup')
        self.assertEqual(r['minutes'], 18)                    # (300 + 600 + 180) / 60
        self.assertEqual(r['dist_m'], 5000)
        self.assertFalse(r['approx'])

    def test_delivery_stage_uses_one_leg(self):
        di, order, rider = self._objs('in_transit')
        with mock.patch.object(eta, '_leg', return_value=(240, 1500, True)) as leg:
            r = eta.for_delivery(di, order, rider)
        self.assertEqual(leg.call_count, 1)
        self.assertEqual((r['minutes'], r['dist_m'], r['approx'], r['arriving']), (4, 1500, True, False))

    def test_result_is_cached(self):
        di, order, rider = self._objs('picked_up')
        with mock.patch.object(eta, '_leg', return_value=(240, 1500, False)) as leg:
            eta.for_delivery(di, order, rider)
            eta.for_delivery(di, order, rider)
        self.assertEqual(leg.call_count, 1)

    def test_no_eta_without_drop_pin_or_rider_location(self):
        self.assertIsNone(eta.for_delivery(*self._objs(drop=False)))
        self.assertIsNone(eta.for_delivery(*self._objs(rider_loc=False)))

    def test_pickup_without_store_location_gives_none(self):
        di, order, rider = self._objs('assigned')
        with mock.patch('app.customer.dispatch._store_coords', return_value=(None, None)):
            self.assertIsNone(eta.for_delivery(di, order, rider))


class RoutingTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_routing_failure_falls_back_and_trips_breaker(self):
        with mock.patch.object(eta.rider_nav, 'fetch_route', side_effect=eta.rider_nav.NavError('down')) as fr:
            s, m, approx = eta._leg((26.2, 50.5), (26.209, 50.5))
            s2, m2, approx2 = eta._leg((26.2, 50.5), (26.209, 50.5))
        self.assertTrue(approx and approx2)
        self.assertEqual(fr.call_count, 1)                  # doosri dafa breaker ki wajah se routing nahi bulayi
        self.assertAlmostEqual(m, 1000 * eta.ROAD_FACTOR, delta=15)

    def test_routing_success_applies_traffic_factor(self):
        with mock.patch.object(eta.rider_nav, 'fetch_route', return_value={'duration_s': 100, 'distance_m': 900}):
            s, m, approx = eta._leg((26.2, 50.5), (26.209, 50.5))
        self.assertEqual((round(s), m, approx), (115, 900.0, False))
