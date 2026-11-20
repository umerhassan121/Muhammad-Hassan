from django.test import SimpleTestCase

from app.customer import rider_nav as n

SAMPLE = {
    'code': 'Ok',
    'routes': [{
        'distance': 1200.4, 'duration': 240.2,
        'geometry': {'coordinates': [[50.5000, 26.2000], [50.5010, 26.2000], [50.5010, 26.2010], [50.5020, 26.2010]]},
        'legs': [{'steps': [
            {'distance': 100, 'name': 'Road 1', 'maneuver': {'type': 'depart', 'location': [50.5, 26.2]}},
            {'distance': 600, 'name': 'Road 2', 'maneuver': {'type': 'turn', 'modifier': 'left', 'location': [50.501, 26.2]}},
            {'distance': 500, 'name': '', 'maneuver': {'type': 'roundabout', 'exit': 2, 'location': [50.501, 26.201]}},
            {'distance': 0, 'name': '', 'maneuver': {'type': 'arrive', 'modifier': 'right', 'location': [50.502, 26.201]}},
        ]}],
    }],
}


class PointTests(SimpleTestCase):
    def test_valid(self):
        self.assertEqual(n.valid_point('26.2', '50.5'), (26.2, 50.5))

    def test_invalid(self):
        for bad in (('', ''), ('abc', '1'), ('95', '10'), ('10', '200'), ('0', '0'), ('nan', '1'), (None, None)):
            with self.assertRaises(n.NavError):
                n.valid_point(*bad)


class InstructionTests(SimpleTestCase):
    def test_turns(self):
        self.assertEqual(n.instruction({'name': 'Main St', 'maneuver': {'type': 'turn', 'modifier': 'left'}}),
                         'Turn left onto Main St')
        self.assertEqual(n.instruction({'maneuver': {'type': 'turn', 'modifier': 'sharp right'}}), 'Turn sharp right')
        self.assertEqual(n.instruction({'maneuver': {'type': 'turn', 'modifier': 'uturn'}}), 'Make a U-turn')
        self.assertEqual(n.instruction({'maneuver': {'type': 'roundabout', 'exit': 3}}),
                         'At the roundabout, take exit 3')
        self.assertEqual(n.instruction({'maneuver': {'type': 'arrive', 'modifier': 'left'}}),
                         'You have arrived on your left')

    def test_unknown_type_does_not_crash(self):
        self.assertEqual(n.instruction({'maneuver': {}}), 'Continue')
        self.assertEqual(n.instruction({}), 'Continue')


class ParseTests(SimpleTestCase):
    def test_parse(self):
        r = n.parse_route(SAMPLE)
        self.assertEqual(r['distance_m'], 1200)
        self.assertEqual(r['duration_s'], 240)
        self.assertEqual(r['line'][0], [26.2, 50.5])          # [lat, lng] (OSRM ka ulta)
        self.assertEqual([s['start_m'] for s in r['steps']], [0, 100, 700, 1200])
        self.assertEqual(r['steps'][1]['text'], 'Turn left onto Road 2')
        self.assertEqual(r['steps'][-1]['arrow'], '🏁')

    def test_no_route(self):
        for bad in ({}, {'code': 'NoRoute'}, {'code': 'Ok', 'routes': []}, None,
                    {'code': 'Ok', 'routes': [{'geometry': {'coordinates': [[1, 2]]}}]}):
            with self.assertRaises(n.NavError):
                n.parse_route(bad)

    def test_thin_keeps_last_point(self):
        pts = [[i, i] for i in range(5000)]
        out = n._thin(pts)
        self.assertLessEqual(len(out), n.MAX_POINTS + 1)
        self.assertEqual(out[-1], pts[-1])


class UrlTests(SimpleTestCase):
    def test_osrm_uses_lng_lat_order(self):
        u = n.route_url('http://osrm', (26.2, 50.5), (26.3, 50.6))
        self.assertIn('/route/v1/driving/50.500000,26.200000;50.600000,26.300000?', u)
