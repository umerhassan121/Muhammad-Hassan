"""Customer Step 4: shop.css ek jagah, customer templates mein inline CSS ka bara hissa nahi."""
import re
from pathlib import Path
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
CSS = ROOT / 'static' / 'css' / 'shop.css'
BASE = ROOT / 'templates' / 'customer_portal' / 'base_shop.html'
MENU = ROOT / 'templates' / 'customer_portal' / '_shop_menu.html'
TILE = ROOT / 'templates' / 'customer_portal' / '_store_tile_css.html'


def _strip(s):
    return re.sub(r'/\*.*?\*/', '', s, flags=re.S)


class ShopCssTests(SimpleTestCase):
    def test_css_file_exists_and_balanced(self):
        css = _strip(CSS.read_text(encoding='utf-8'))
        self.assertGreater(len(css), 50000)
        self.assertEqual(css.count('{'), css.count('}'))

    def test_has_sections_and_tokens(self):
        css = CSS.read_text(encoding='utf-8')
        for marker in ('--shop-tap', '.sm-bar', '.stl ', '.voice-lang-btn', '.shop-navbar'):
            self.assertIn(marker, css)

    def test_base_links_shop_css_and_is_small(self):
        base = BASE.read_text(encoding='utf-8')
        self.assertIn("css/shop.css", base)
        self.assertLess(len(base), 100000)
        # base_shop mein bara <style> nahi (sirf chhote flag wale)
        for block in re.findall(r'<style>(.*?)</style>', base, flags=re.S):
            self.assertLess(len(block), 400)

    def test_menu_and_tile_have_no_inline_style(self):
        self.assertNotIn('<style', MENU.read_text(encoding='utf-8'))
        self.assertNotIn('<style', TILE.read_text(encoding='utf-8'))


class CartCheckoutCssTests(SimpleTestCase):
    """Customer Step 5: cart / checkout ka CSS alag file mein, tap size 44px+, bar ka takrao nahi."""

    def _t(self, name):
        return (ROOT / 'templates' / 'customer_portal' / name).read_text(encoding='utf-8')

    def _c(self, name):
        return (ROOT / 'static' / 'css' / name).read_text(encoding='utf-8')

    def test_pages_link_own_css_and_have_no_style_block(self):
        for page, css in (('cart.html', 'shop_cart.css'), ('checkout.html', 'shop_checkout.css')):
            t = self._t(page)
            self.assertIn(css, t)
            self.assertNotIn('<style', t)
            c = _strip(self._c(css))
            self.assertEqual(c.count('{'), c.count('}'))

    def test_cart_qty_and_remove_are_44px(self):
        c = self._c('shop_cart.css')
        self.assertIn('.qty-btn { width: 44px;', c)
        self.assertIn('height: 44px; }', c)
        self.assertNotIn('.qty-btn { width: 32px; }', c)
        self.assertIn('min-height: 44px', c)

    def test_cart_bar_has_safe_area_and_reason(self):
        self.assertIn('safe-area-inset-bottom', self._c('shop_cart.css'))
        t = self._t('cart.html')
        self.assertIn('mobile-checkout-why', t)

    def test_checkout_blocked_reason_and_safe_area(self):
        t = self._t('checkout.html')
        self.assertEqual(t.count('class="co-why"'), 2)
        c = self._c('shop_checkout.css')
        self.assertIn('safe-area-inset-bottom', c)
        self.assertIn('.co-why', c)


class Step6PagesCssTests(SimpleTestCase):
    """Customer Step 6: baqi pages ka CSS apni file mein, tap size 44px+, menu mapping."""

    PAGES = [
        'store_detail.html', 'product_detail.html', 'my_orders.html', 'order_detail.html',
        'order_tracking.html', 'wallet.html', 'favorites.html', 'repeat_plans.html', 'pro.html',
        'account/dashboard.html', 'auth/login.html', 'auth/register.html', 'auth/forgot_password.html',
        'auth/reset_password.html', 'auth/verify_login_otp.html', 'auth/verify_otp_later.html',
        'auth/pending_otps.html', 'info/base_info.html',
    ]

    def test_pages_link_existing_css_and_have_no_style_block(self):
        base = ROOT / 'templates' / 'customer_portal'
        for page in self.PAGES:
            t = (base / page).read_text(encoding='utf-8')
            self.assertNotIn('<style', t, page)
            m = re.search(r"static 'css/(shop_[a-z_]+\.css)'", t)
            self.assertIsNotNone(m, page)
            css = ROOT / 'static' / 'css' / m.group(1)
            self.assertTrue(css.exists(), m.group(1))
            c = _strip(css.read_text(encoding='utf-8'))
            self.assertEqual(c.count('{'), c.count('}'), m.group(1))

    def test_tap_sizes(self):
        css = ROOT / 'static' / 'css'
        self.assertIn('.pd-qty button{width:44px;height:44px}', (css / 'shop_product_detail.css').read_text(encoding='utf-8'))
        self.assertIn('.sd-back{width:44px;height:44px}', (css / 'shop_store_detail.css').read_text(encoding='utf-8'))
        self.assertIn('.fv-tab{min-height:44px', (css / 'shop_favorites.css').read_text(encoding='utf-8'))

    def test_menu_mapping_covers_auth_and_live_tracking(self):
        from app.customer.shop_menu import TAB_FOR_URL
        for name in ('forgot_password', 'reset_password', 'verify_otp_later'):
            self.assertEqual(TAB_FOR_URL[name], 'account')
        self.assertEqual(TAB_FOR_URL['track_live_public'], 'orders')
