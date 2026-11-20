"""Vendor navigation (Step 1): role ke hisaab se menu, flags, active group, aur URL names ka asli hona."""
from django.test import SimpleTestCase
from django.urls import reverse

from app.customer import vendor_nav as nav
from app.customer.vendor_access import OWNER_ONLY, ORDERS_ROLE_ALLOWED


def _flags_on(name):
    return True


def _flags_off(name):
    return False


def _urls(data):
    return [i['url_name'] for g in data['groups'] for i in g['items']]


class NavMapTests(SimpleTestCase):
    def test_every_url_name_exists(self):
        names = {'vendor_dashboard', 'vendor_logout'}
        for g in nav.NAV_GROUPS:
            names |= set(g.get('also', ()))
            for it in g['items']:
                names.add(it['url_name'])
                names |= set(it.get('also', ()))
        for name in sorted(names):
            if name in ('vendor_dispute_detail', 'vendor_statement', 'vendor_support_detail', 'vendor_order_action',
                        'vendor_order_receipt', 'vendor_order_escpos', 'vendor_assign_rider', 'vendor_product_edit',
                        'vendor_product_options', 'vendor_product_toggle', 'vendor_product_action', 'vendor_deal_end',
                        'vendor_payout_cancel', 'vendor_branch_action', 'vendor_branch_copy', 'vendor_staff_action',
                        'vendor_reply_review', 'vendor_statement_pdf'):
                continue                      # inhein id/argument chahiye - sirf naam ka wujood neeche dekha
            reverse(name)

    def test_no_item_listed_twice(self):
        seen = []
        for g in nav.NAV_GROUPS:
            seen += [i['url_name'] for i in g['items']]
        self.assertEqual(len(seen), len(set(seen)))

    def test_group_keys_cover_tabs(self):
        keys = {g['key'] for g in nav.NAV_GROUPS}
        self.assertEqual(keys, set(nav.TAB_GROUPS) | set(nav.MORE_GROUPS))


class RoleTests(SimpleTestCase):
    def test_owner_sees_everything(self):
        data = nav.build_nav('owner', flag=_flags_on)
        self.assertEqual({g['key'] for g in data['groups']}, {g['key'] for g in nav.NAV_GROUPS})
        self.assertIn('vendor_pos', _urls(data))
        self.assertIn('vendor_statements', _urls(data))

    def test_manager_has_no_owner_only_items(self):
        urls = _urls(nav.build_nav('manager', flag=_flags_on))
        self.assertTrue(urls)
        self.assertFalse(set(urls) & OWNER_ONLY)
        self.assertIn('vendor_reports', urls)

    def test_orders_role_only_orders_pages(self):
        data = nav.build_nav('orders', flag=_flags_on)
        urls = _urls(data)
        self.assertTrue(set(urls) <= ORDERS_ROLE_ALLOWED)
        self.assertEqual([g['key'] for g in data['groups']], ['orders'])
        self.assertEqual([t['key'] for t in data['tabs']], ['home', 'orders'])

    def test_unknown_role_gets_nothing(self):
        data = nav.build_nav(None, flag=_flags_on)
        self.assertEqual(data['groups'], [])
        self.assertEqual(data['tabs'], [])


class VisibilityTests(SimpleTestCase):
    def test_flags_hide_deals_and_promote(self):
        urls = _urls(nav.build_nav('owner', flag=_flags_off))
        self.assertNotIn('vendor_deals', urls)
        self.assertNotIn('vendor_promote', urls)
        self.assertIn('vendor_offers', urls)

    def test_unapproved_store_hides_selling_tools(self):
        urls = _urls(nav.build_nav('owner', is_approved=False, flag=_flags_on))
        for name in ('vendor_product_add', 'vendor_offers', 'vendor_deals', 'vendor_promote'):
            self.assertNotIn(name, urls)
        self.assertIn('vendor_menu', urls)


class ActiveAndBadgeTests(SimpleTestCase):
    def test_active_group_and_item(self):
        data = nav.build_nav('owner', current='vendor_item_schedule', flag=_flags_on)
        active = [g['key'] for g in data['groups'] if g['active']]
        self.assertEqual(active, ['menu'])
        item = [i for g in data['groups'] for i in g['items'] if i['active']]
        self.assertEqual([i['url_name'] for i in item], ['vendor_item_schedule'])

    def test_secondary_page_keeps_group_active(self):
        data = nav.build_nav('owner', current='vendor_order_receipt', flag=_flags_on)
        self.assertEqual([g['key'] for g in data['groups'] if g['active']], ['orders'])

    def test_home_tab_active_on_dashboard(self):
        data = nav.build_nav('owner', current='vendor_dashboard', flag=_flags_on)
        self.assertEqual([t['key'] for t in data['tabs'] if t['active']], ['home'])

    def test_more_tab_active_for_store_pages(self):
        data = nav.build_nav('owner', current='vendor_staff', flag=_flags_on)
        self.assertEqual([t['key'] for t in data['tabs'] if t['active']], ['more'])

    def test_tabs_order_and_landing(self):
        data = nav.build_nav('owner', flag=_flags_on)
        self.assertEqual([t['key'] for t in data['tabs']], ['home', 'orders', 'menu', 'money', 'more'])
        money = [t for t in data['tabs'] if t['key'] == 'money'][0]
        self.assertEqual(money['url_name'], 'vendor_reports')

    def test_badges(self):
        data = nav.build_nav('owner', flag=_flags_on, badges={'new_orders': 3, 'dispute_pending': 1})
        orders = [t for t in data['tabs'] if t['key'] == 'orders'][0]
        self.assertEqual(orders['badge'], 4)
        self.assertEqual(nav.build_nav('owner', flag=_flags_on)['tabs'][1]['badge'], 0)
