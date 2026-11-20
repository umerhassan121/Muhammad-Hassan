"""Customer shop menu (Step 2): kaun sa tab kab dikhe, kahan bar chhupe, vendor / rider par purana chrome."""
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from app.customer import shop_menu as sm


def _req(url_name, authed=False, path='/shop/', cart=None, customer=False):
    user = SimpleNamespace(is_authenticated=authed)
    if customer:
        user.customer_profile = SimpleNamespace(customer=object())
    return SimpleNamespace(user=user, path=path, session={'cart': cart or {}},
                           resolver_match=SimpleNamespace(url_name=url_name) if url_name else None)


def _labels(tabs):
    return [t['label'] for t in tabs]


class PageRulesTests(SimpleTestCase):
    def test_customer_pages_get_menu(self):
        for name in ('shop_home', 'store_list', 'my_orders', 'wallet_page', 'customer_login'):
            self.assertTrue(sm.is_menu_page(_req(name)), name)

    def test_vendor_and_rider_pages_keep_old_chrome(self):
        self.assertFalse(sm.is_menu_page(_req('vendor_orders', path='/shop/vendor/orders/')))
        self.assertFalse(sm.is_menu_page(_req('rider_home', path='/shop/rider/')))
        self.assertFalse(sm.is_menu_page(_req('pos_orders', path='/shop/vendor/pos-api/orders/')))

    def test_unknown_page_keeps_old_chrome(self):
        self.assertFalse(sm.is_menu_page(_req(None)))

    def test_bar_hidden_on_cart_checkout_place_order_only(self):
        for name in ('cart_view', 'checkout', 'place_order'):
            self.assertTrue(sm.is_bar_hidden(_req(name)), name)
        for name in ('shop_home', 'shop_product_detail', 'order_tracking', 'my_orders'):
            self.assertFalse(sm.is_bar_hidden(_req(name)), name)

    def test_flags_context(self):
        self.assertEqual(sm.menu_flags(_req('cart_view')), {'SHOP_MENU_ON': True, 'SHOP_BAR_ON': False})
        self.assertEqual(sm.menu_flags(_req('shop_home')), {'SHOP_MENU_ON': True, 'SHOP_BAR_ON': True})
        self.assertEqual(sm.menu_flags(_req('vendor_orders', path='/shop/vendor/orders/')),
                         {'SHOP_MENU_ON': False, 'SHOP_BAR_ON': False})


class TabTests(SimpleTestCase):
    def setUp(self):
        p = mock.patch('django.urls.reverse', side_effect=lambda n, *a, **k: '/' + n + '/')
        p.start()
        self.addCleanup(p.stop)

    def test_cart_count_sums_quantities(self):
        self.assertEqual(sm.cart_count(_req('shop_home', cart={'1': {'quantity': 2}, '2': {'quantity': 3}})), 5)

    def test_guest_has_track_not_orders_and_five_tabs(self):
        tabs = sm.build_tabs(_req('shop_home'), {})
        self.assertEqual(_labels(tabs), ['Home', 'Stores', 'Cart', 'Track', 'Account'])

    def test_guest_without_tracking_loses_the_tab(self):
        tabs = sm.build_tabs(_req('shop_home'), {'order_tracking_enabled': False, 'shop_stores_enabled': True})
        self.assertEqual(_labels(tabs), ['Home', 'Stores', 'Cart', 'Account'])

    def test_stores_off_gives_four_tabs(self):
        with mock.patch.object(sm, 'active_orders_count', return_value=0), \
                mock.patch.object(sm, 'orders_on_the_way', return_value=False):
            tabs = sm.build_tabs(_req('shop_home', authed=True, customer=True), {'shop_stores_enabled': False})
        self.assertEqual(_labels(tabs), ['Home', 'Cart', 'Orders', 'Account'])

    def test_customer_has_orders_with_active_badge(self):
        with mock.patch.object(sm, 'active_orders_count', return_value=2), \
                mock.patch.object(sm, 'orders_on_the_way', return_value=True):
            tabs = sm.build_tabs(_req('my_orders', authed=True, customer=True), {})
        self.assertEqual(_labels(tabs), ['Home', 'Stores', 'Cart', 'Orders', 'Account'])
        orders = [t for t in tabs if t['key'] == 'orders'][0]
        self.assertEqual(orders['badge'], 2)
        self.assertTrue(orders['live'])
        self.assertTrue(orders['active'])

    def test_cart_is_in_the_middle_with_badge(self):
        tabs = sm.build_tabs(_req('shop_home', cart={'1': {'quantity': 4}}), {})
        self.assertEqual(tabs[2]['key'], 'cart')
        self.assertEqual(tabs[2]['badge'], 4)

    def test_active_tab_follows_page(self):
        self.assertEqual([t['key'] for t in sm.build_tabs(_req('wallet_page'), {}) if t['active']], ['account'])
        self.assertEqual([t['key'] for t in sm.build_tabs(_req('store_detail'), {}) if t['active']], ['stores'])
        self.assertEqual([t['key'] for t in sm.build_tabs(_req('shop_product_detail'), {}) if t['active']], ['home'])
