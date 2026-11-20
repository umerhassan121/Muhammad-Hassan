"""Vendor dashboard (Step 3): KPI cards aur alerts ke qaide."""
from django.test import SimpleTestCase

from app.utils import vendor_dashboard_rules as r


class KpiTests(SimpleTestCase):
    def test_no_data_shows_dash_not_zero(self):
        cards = {c['key']: c for c in r.kpi_cards(None, None)}
        self.assertEqual(cards['orders']['value'], '0')
        self.assertEqual(cards['accept']['value'], '-')
        self.assertEqual(cards['rating']['value'], '-')
        self.assertEqual(cards['score']['value'], '-')
        self.assertEqual(cards['accept']['tone'], 'na')

    def test_values_and_tones(self):
        today = {'orders': 12, 'pending': 2}
        week = {'orders': 80, 'accept_rate': 95.0, 'rating': 4.5, 'rating_n': 20, 'score': 88.4}
        cards = {c['key']: c for c in r.kpi_cards(today, week)}
        self.assertEqual(cards['orders']['value'], '12')
        self.assertEqual(cards['orders']['tone'], 'warn')
        self.assertIn('2 waiting', cards['orders']['sub'])
        self.assertEqual(cards['accept']['value'], '95%')
        self.assertEqual(cards['accept']['tone'], 'good')
        self.assertEqual(cards['rating']['value'], '4.5 / 5')
        self.assertEqual(cards['score']['value'], '88 / 100')
        self.assertEqual(cards['score']['tone'], 'good')

    def test_bad_accept_rate_is_red(self):
        cards = {c['key']: c for c in r.kpi_cards({}, {'accept_rate': 55.5, 'orders': 10})}
        self.assertEqual(cards['accept']['value'], '55.5%')
        self.assertEqual(cards['accept']['tone'], 'bad')

    def test_all_handled_is_good(self):
        cards = {c['key']: c for c in r.kpi_cards({'orders': 3, 'pending': 0}, {})}
        self.assertEqual(cards['orders']['tone'], 'good')


class AlertTests(SimpleTestCase):
    def test_nothing_to_report(self):
        self.assertEqual(r.alerts(), [])

    def test_order_and_dispute_alerts(self):
        out = r.alerts(new_orders=1, dispute_pending=2)
        self.assertEqual([a['url_name'] for a in out], ['vendor_orders', 'vendor_disputes'])
        self.assertEqual(out[0]['text'], '1 new order waiting for your answer.')
        self.assertEqual(out[1]['text'], '2 disputes need your reply.')
        self.assertTrue(all(a['level'] == 'danger' for a in out))

    def test_singular_dispute_grammar(self):
        self.assertEqual(r.alerts(dispute_pending=1)[0]['text'], '1 dispute needs your reply.')

    def test_stock_and_pause(self):
        out = r.alerts(out_count=2, low_count=1, is_paused=True)
        self.assertEqual([a['level'] for a in out], ['warn', 'warn', 'warn'])
        self.assertEqual(out[0]['text'], '2 products sold out.')
        self.assertEqual(out[1]['text'], '1 product running low.')

    def test_unapproved_store(self):
        out = r.alerts(is_approved=False)
        self.assertEqual(out[0]['level'], 'info')

    def test_order_priority(self):
        out = r.alerts(new_orders=3, dispute_pending=1, out_count=1, is_approved=False)
        self.assertEqual([a['url_name'] for a in out], ['vendor_help', 'vendor_orders', 'vendor_disputes', 'vendor_menu'])
