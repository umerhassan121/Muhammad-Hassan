from django.test import SimpleTestCase

from app.customer import batch_nav as bn
from app.customer import batching as b
from app.customer import rider_nav as n


def O(i, status, vendor, store_ll, drop_ll, name='C'):
    return {'order_no': 100 + i, 'order_id': i, 'status': status, 'vendor_id': vendor, 'store_name': f'Store{vendor}',
            'store_ll': store_ll, 'store_addr': '', 'cust_name': name, 'drop_ll': drop_ll, 'cust_addr': ''}


def _precedence_ok(stops):
    picked = set()
    for s in stops:
        for oid in s['order_ids']:
            if s['kind'] == 'pickup':
                picked.add(oid)
            elif oid not in picked and s.get('needs_pickup', True):
                return False
    return True


class SequenceTests(SimpleTestCase):
    def test_interleaves_when_shorter(self):
        # do door door store, har ek ke paas apna customer: P1 D1 P2 D2 (P1 P2 D1 D2 se kam doori)
        orders = [O(1, 'assigned', 1, (26.20, 50.50), (26.21, 50.50), 'A'),
                  O(2, 'assigned', 2, (26.40, 50.60), (26.41, 50.60), 'B')]
        plan = b.plan_route(orders, start=(26.19, 50.50))
        self.assertEqual([(s['kind'], s['label']) for s in plan['stops']],
                         [('pickup', 'Store1'), ('drop', 'A'), ('pickup', 'Store2'), ('drop', 'B')])

    def test_drop_never_before_its_pickup(self):
        import random
        rnd = random.Random(7)
        for _ in range(100):
            orders = [O(i, 'assigned', rnd.randint(1, 3), (26 + rnd.random() * .2, 50 + rnd.random() * .2),
                        (26 + rnd.random() * .2, 50 + rnd.random() * .2)) for i in range(1, 5)]
            self.assertTrue(_precedence_ok(b.plan_route(orders, start=(26.1, 50.1))['stops']))

    def test_lock_keeps_current_stop_first(self):
        orders = [O(1, 'assigned', 1, (26.20, 50.50), (26.21, 50.50), 'A'),
                  O(2, 'assigned', 2, (26.40, 50.60), (26.41, 50.60), 'B')]
        plan = b.plan_route(orders, start=(26.19, 50.50), lock_first='p:2')
        self.assertEqual(plan['stops'][0]['label'], 'Store2')
        self.assertEqual(plan['stops'][0]['key'], 'p:2')

    def test_lock_on_drop_with_pending_pickup_is_ignored(self):
        orders = [O(1, 'assigned', 1, (26.20, 50.50), (26.21, 50.50), 'A')]
        plan = b.plan_route(orders, start=(26.19, 50.50), lock_first='d:1', min_orders=1)
        self.assertEqual(plan['stops'][0]['kind'], 'pickup')

    def test_single_order_plan_and_min_orders(self):
        one = [O(1, 'picked_up', 1, (26.2, 50.5), (26.3, 50.6))]
        self.assertIsNone(b.plan_route(one))
        self.assertEqual(len(b.plan_route(one, min_orders=1)['stops']), 1)

    def test_unlocated_pickup_first_unlocated_drop_last(self):
        orders = [O(1, 'assigned', 1, None, (26.2, 50.5), 'A'),
                  O(2, 'assigned', 2, (26.3, 50.6), None, 'B')]
        orders[0]['store_addr'] = 'Shop 1'
        orders[1]['cust_addr'] = 'Flat 9'
        plan = b.plan_route(orders, start=(26.1, 50.4))
        self.assertEqual(plan['stops'][0]['label'], 'Store1')           # location nahi: pehle
        self.assertEqual(plan['stops'][-1]['label'], 'B')               # location nahi: aakhir

    def test_many_orders_falls_back_to_greedy(self):
        orders = [O(i, 'assigned', i, (26 + i * .01, 50), (26 + i * .01, 50.1)) for i in range(1, 7)]
        plan = b.plan_route(orders, start=(26, 50))
        self.assertEqual(len(plan['stops']), 12)
        self.assertTrue(_precedence_ok(plan['stops']))


class AnnotateTests(SimpleTestCase):
    def test_eta_includes_dwell(self):
        stops = [{'kind': 'pickup', 'order_ids': [1]}, {'kind': 'drop', 'order_ids': [1]}]
        legs = [{'distance_m': 1000, 'duration_s': 120}, {'distance_m': 2000, 'duration_s': 300}]
        bn.annotate(stops, legs)
        self.assertEqual(stops[0]['eta_s'], 120)
        self.assertEqual(stops[1]['eta_s'], 120 + bn.DWELL_PICKUP_S + 300)
        self.assertEqual(stops[1]['dist_m'], 3000)

    def test_stops_before(self):
        stops = [{'kind': 'pickup', 'order_ids': [1, 2]}, {'kind': 'drop', 'order_ids': [2]}, {'kind': 'drop', 'order_ids': [1]}]
        self.assertEqual(bn.stops_before(stops, 1), 2)
        self.assertEqual(bn.stops_before(stops, 2), 1)
        self.assertIsNone(bn.stops_before(stops, 9))


MULTI = {
    'code': 'Ok',
    'routes': [{
        'distance': 3000, 'duration': 600,
        'geometry': {'coordinates': [[50.50, 26.20], [50.51, 26.20], [50.51, 26.21], [50.52, 26.21]]},
        'legs': [
            {'distance': 1000, 'duration': 200, 'steps': [
                {'distance': 1000, 'name': 'A', 'maneuver': {'type': 'depart', 'location': [50.50, 26.20]}},
                {'distance': 0, 'name': '', 'maneuver': {'type': 'arrive', 'location': [50.51, 26.20]}}]},
            {'distance': 2000, 'duration': 400, 'steps': [
                {'distance': 2000, 'name': 'B', 'maneuver': {'type': 'depart', 'location': [50.51, 26.20]}},
                {'distance': 0, 'name': '', 'maneuver': {'type': 'arrive', 'location': [50.52, 26.21]}}]},
        ],
    }],
}


class MultiRouteTests(SimpleTestCase):
    def test_legs_and_step_leg_index(self):
        r = n.parse_route(MULTI)
        self.assertEqual([l['end_m'] for l in r['legs']], [1000, 3000])
        self.assertEqual([s['leg'] for s in r['steps']], [0, 0, 1, 1])
        self.assertEqual([s['start_m'] for s in r['steps']], [0, 1000, 1000, 3000])

    def test_points_url_has_all_waypoints(self):
        url = n.points_url('http://osrm', [(26.2, 50.5), (26.3, 50.6), (26.4, 50.7)])
        self.assertIn('50.500000,26.200000;50.600000,26.300000;50.700000,26.400000', url)

    def test_cap_steps_keeps_depart_and_arrive(self):
        steps = ([{'type': 'depart'}] + [{'type': 'continue'} for _ in range(20)] +
                 [{'type': 'turn'} for _ in range(5)] + [{'type': 'arrive'}, {'type': 'depart'}, {'type': 'arrive'}])
        out = n.cap_steps(steps, 12)
        self.assertEqual(len(out), 12)
        self.assertEqual(sum(1 for s in out if s['type'] == 'arrive'), 2)
        self.assertEqual(sum(1 for s in out if s['type'] == 'depart'), 2)
        self.assertEqual(sum(1 for s in out if s['type'] == 'turn'), 5)      # asli mor pehle bachte hain

    def test_arabic_instructions(self):
        self.assertEqual(n.instruction({'name': 'Road 1', 'maneuver': {'type': 'turn', 'modifier': 'left'}}, 'ar'),
                         'انعطف يسارًا إلى Road 1')
        self.assertEqual(n.instruction({'maneuver': {'type': 'arrive', 'modifier': 'right'}}, 'ar'), 'لقد وصلت على يمينك')
        self.assertEqual(n.instruction({'maneuver': {'type': 'turn', 'modifier': 'left'}}), 'Turn left')   # default English


class DeliveryEtaBatchTests(SimpleTestCase):
    def test_batch_total_adds_dwell_only_for_intermediate_stops(self):
        from app.customer import delivery_eta as eta
        pts = [(26.2, 50.5), (26.21, 50.5), (26.22, 50.5)]
        sec, meters, approx = eta.batch_total(pts, ['pickup', 'drop'], lambda a, b_: (100, 1000, False))
        self.assertEqual(sec, 100 + bn.DWELL_PICKUP_S + 100)
        self.assertEqual(meters, 2000)
        self.assertFalse(approx)
        self.assertTrue(eta.batch_total(pts, ['pickup', 'drop'], lambda a, b_: (1, 1, True))[2])
