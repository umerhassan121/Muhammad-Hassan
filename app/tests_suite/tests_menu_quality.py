"""
Tests: Menu quality rules (app/utils/menu_quality_rules.py). Pure Python - no database.

Run:  python manage.py test app.tests_suite.tests_menu_quality -v 2
Hand-calculated: photo 40 + description 35 + name 25 = 100.
"""
from django.test import SimpleTestCase

from app.utils import menu_quality_rules as r

LONG = 'Slow cooked chicken with basmati rice and raita'


class ItemTests(SimpleTestCase):
    def test_complete_item_is_100(self):
        self.assertEqual(r.item_check('Chicken Biryani', LONG, True), {'score': 100, 'issues': []})

    def test_missing_parts_and_scores(self):
        self.assertEqual(r.item_check('Chicken Biryani', LONG, False), {'score': 60, 'issues': ['photo']})
        self.assertEqual(r.item_check('Chicken Biryani', '', True), {'score': 65, 'issues': ['desc']})
        self.assertEqual(r.item_check('TEST', LONG, True), {'score': 75, 'issues': ['name']})
        self.assertEqual(r.item_check('', None, False), {'score': 0, 'issues': ['photo', 'desc', 'name']})

    def test_short_description_does_not_count(self):
        self.assertIn('desc', r.item_check('Chicken Biryani', 'tasty', True)['issues'])
        self.assertNotIn('desc', r.item_check('Chicken Biryani', 'x' * 20, True)['issues'])

    def test_name_rules(self):
        self.assertTrue(r.name_ok('Tea'.ljust(4, 'a')))          # exactly 4 chars
        self.assertFalse(r.name_ok('Tea'))                        # too short
        self.assertFalse(r.name_ok('CHICKEN BIRYANI'))            # shouting
        self.assertTrue(r.name_ok('BBQ'.ljust(3) + ' Wrap'))      # short caps word inside a normal name
        self.assertFalse(r.name_ok('1234'))                       # no letters
        self.assertFalse(r.name_ok('demo'))                       # junk
        self.assertFalse(r.name_ok('x' * 61))


class SummaryTests(SimpleTestCase):
    def test_empty_menu(self):
        s = r.summarize([])
        self.assertIsNone(s['score'])
        self.assertIsNone(s['complete_pct'])

    def test_summary_numbers(self):
        rows = [r.item_check('Chicken Biryani', LONG, True),     # 100, complete
                r.item_check('Chicken Karahi', LONG, False),     # 60, no photo
                r.item_check('Tea', '', False)]                  # 0 -> all 3 issues? name 'Tea' too short
        s = r.summarize(rows)
        self.assertEqual(s['items'], 3)
        self.assertEqual(s['score'], round((100 + 60 + 0) / 3))
        self.assertEqual((s['complete'], s['complete_pct']), (1, 33))
        self.assertEqual((s['missing_photo'], s['missing_desc'], s['bad_name']), (2, 1, 1))

    def test_labels(self):
        self.assertEqual(r.label(80), ('Good', 'good'))
        self.assertEqual(r.label(79), ('Fair', 'warn'))
        self.assertEqual(r.label(50), ('Fair', 'warn'))
        self.assertEqual(r.label(49), ('Needs work', 'bad'))
