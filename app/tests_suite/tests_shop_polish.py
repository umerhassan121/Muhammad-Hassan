"""Customer home polish (v10): category icons, one language toggle, clean URL, skeleton, RTL, PWA install."""
import re
from pathlib import Path
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
T = ROOT / 'templates'
S = ROOT / 'static'


def _read(p):
    return p.read_text(encoding='utf-8')


class ShopPolishTests(SimpleTestCase):
    def test_cat_icon_by_name_with_fallback(self):
        from app.templatetags.shop_ui import cat_icon
        self.assertEqual(cat_icon('Juice', 0), 'bi-cup-straw')
        self.assertEqual(cat_icon('Fresh Fruits', 1), 'bi-apple')
        self.assertNotEqual(cat_icon('Steak House', 0), 'bi-cup-hot-fill')   # "tea" shabd ke beech mein nahi
        self.assertTrue(cat_icon('Misc', 3).startswith('bi-'))
        self.assertTrue(cat_icon(None, 0).startswith('bi-'))

    def test_polish_css_balanced_and_linked(self):
        css = re.sub(r'/\*.*?\*/', '', _read(S / 'css' / 'shop_polish.css'), flags=re.S)
        self.assertEqual(css.count('{'), css.count('}'))
        base = _read(T / 'customer_portal' / 'base_shop.html')
        self.assertIn('css/shop_polish.css', base)
        self.assertIn('js/shop_polish.js', base)
        for block in re.findall(r'<style>(.*?)</style>', base, flags=re.S):
            self.assertLess(len(block), 400)

    def test_only_one_language_switch_on_home(self):
        for name in ('shop.html', 'base_shop.html', 'stores.html', 'store_detail.html'):
            self.assertNotIn('class="voice-lang-btn', _read(T / 'customer_portal' / name), name)
        base = _read(T / 'customer_portal' / 'base_shop.html')
        self.assertNotIn("localStorage.getItem('shopVoiceLang')", base)

    def test_home_uses_icon_filter_and_trust_row(self):
        home = _read(T / 'customer_portal' / 'shop.html')
        self.assertIn('cat_icon', home)
        self.assertIn('info-wa', home)
        self.assertLess(home.index('info-strip">'), home.index('id="promoTrack"'))
        self.assertNotIn('<span class="hero-eyebrow">', home)

    def test_js_cleans_hash_and_has_skeleton(self):
        js = _read(S / 'js' / 'shop_polish.js')
        self.assertIn('replaceState', js)
        self.assertIn('sk-on', js)

    def test_rtl_and_urdu_font_rules(self):
        css = _read(S / 'css' / 'shop_polish.css')
        self.assertIn('html[dir=rtl]', css)
        self.assertIn('Noto Nastaliq Urdu', css)

    def test_pwa_install_entry(self):
        self.assertNotIn('data-pwa-install', _read(T / 'customer_portal' / '_shop_menu.html'))
        self.assertIn('navInstallApp', _read(T / 'customer_portal' / 'base_shop.html'))
        pwa = _read(T / 'pwa' / '_pwa.html')
        self.assertIn('--pwa-lift', pwa)
        self.assertNotIn('App install karein', pwa)


class TabBarV11Tests(SimpleTestCase):
    def test_quick_access_grid_in_sheet(self):
        menu = _read(T / 'customer_portal' / '_shop_menu.html')
        self.assertIn('class="sm-quick"', menu)
        self.assertEqual(menu.count('class="sm-q"'), 4)
        self.assertIn('sm-live', menu)

    def test_live_flag_and_urdu_label_css(self):
        from app.customer import shop_menu as sm
        self.assertEqual(sm.ON_THE_WAY_STATUSES, ['picked_up', 'in_transit'])
        css = _read(S / 'css' / 'shop_polish.css')
        self.assertIn('html[lang=ur] body .sm-lbl', css)
        self.assertIn('.sm-live', css)
