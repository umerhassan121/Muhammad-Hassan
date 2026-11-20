"""Vendor menu tag (Step 2): kab dikhe, kab chhupe, aur template theek render ho."""
from types import SimpleNamespace
from unittest import mock

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from app.customer import vendor_nav as nav
from app.templatetags import vendor_nav_tags as tags


def _req(url_name, authed=True):
    return SimpleNamespace(user=SimpleNamespace(is_authenticated=authed),
                           resolver_match=SimpleNamespace(url_name=url_name))


def _profile(approved=True):
    return SimpleNamespace(vendor=object(), is_approved=approved)


PATCH = 'app.customer.vendor_access.'


class ContextTests(SimpleTestCase):
    def test_hidden_outside_vendor_pages(self):
        self.assertIsNone(tags.vendor_nav_context(_req('shop_home')))
        self.assertIsNone(tags.vendor_nav_context(_req(None)))

    def test_hidden_on_login_and_register(self):
        self.assertIsNone(tags.vendor_nav_context(_req('vendor_login')))
        self.assertIsNone(tags.vendor_nav_context(_req('vendor_register')))

    def test_hidden_when_not_logged_in(self):
        self.assertIsNone(tags.vendor_nav_context(_req('vendor_orders', authed=False)))

    def test_hidden_when_user_is_not_a_vendor(self):
        with mock.patch(PATCH + 'get_vendor_profile', return_value=None):
            self.assertIsNone(tags.vendor_nav_context(_req('vendor_orders')))

    def test_owner_gets_menu_with_badges(self):
        with mock.patch(PATCH + 'get_vendor_profile', return_value=_profile()), \
             mock.patch(PATCH + 'vendor_role', return_value='owner'), \
             mock.patch.object(tags, '_badges', return_value={'new_orders': 2}), \
             mock.patch.object(nav, '_default_flag', return_value=True):
            data = tags.vendor_nav_context(_req('vendor_orders'))
        self.assertEqual([t['key'] for t in data['tabs']], ['home', 'orders', 'menu', 'money', 'more'])
        self.assertEqual(data['tabs'][1]['badge'], 2)
        self.assertTrue(data['tabs'][1]['active'])

    def test_orders_role_gets_short_menu(self):
        with mock.patch(PATCH + 'get_vendor_profile', return_value=_profile()), \
             mock.patch(PATCH + 'vendor_role', return_value='orders'), \
             mock.patch.object(tags, '_badges', return_value={}), \
             mock.patch.object(nav, '_default_flag', return_value=True):
            data = tags.vendor_nav_context(_req('vendor_orders'))
        self.assertEqual([t['key'] for t in data['tabs']], ['home', 'orders'])

    def test_tag_never_breaks_the_page(self):
        ctx = {'request': _req('vendor_orders')}
        with mock.patch.object(tags, 'vendor_nav_context', side_effect=RuntimeError('boom')):
            self.assertEqual(tags.vendor_nav({'request': ctx['request']}), {'nav': None})
        self.assertEqual(tags.vendor_nav({}), {'nav': None})


class TemplateTests(SimpleTestCase):
    TEMPLATE = 'customer_portal/vendor/_vendor_nav.html'

    def _render(self, role):
        data = nav.build_nav(role, current='vendor_orders', flag=lambda n: True, badges={'new_orders': 3})
        return render_to_string(self.TEMPLATE, {'nav': data})

    def test_empty_when_no_nav(self):
        self.assertEqual(render_to_string(self.TEMPLATE, {'nav': None}).strip(), '')

    def test_owner_has_more_button_and_side_menu(self):
        html = self._render('owner')
        self.assertIn('vnavMoreBtn', html)
        self.assertIn('vnav-side', html)
        self.assertIn('/shop/vendor/menu-quality/', html)
        self.assertIn('>3<', html)               # new orders badge

    def test_orders_role_has_no_more_button(self):
        html = self._render('orders')
        self.assertNotIn('vnavMoreBtn', html)
        self.assertNotIn('/shop/vendor/staff/', html)
