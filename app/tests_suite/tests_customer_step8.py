"""Customer Step 8: khali / error screens, internet patti, double-order se bachao (files ka dhancha + Urdu)."""
import re
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
TPL = ROOT / 'templates' / 'customer_portal'
INCLUDE = re.compile(r"\{% include 'customer_portal/_empty_state\.html' with (.*?) %\}", re.S)
STR_ARG = re.compile(r"\b(title|text|cta_label|cta2_label)='([^']*)'")


def _read(p):
    return Path(p).read_text(encoding='utf-8')


class CustomerStep8Assets(SimpleTestCase):
    def test_files_and_css(self):
        self.assertTrue((ROOT / 'static' / 'js' / 'shop_ux.js').exists())
        self.assertTrue((TPL / '_empty_state.html').exists())
        css = _read(ROOT / 'static' / 'css' / 'shop.css')
        for cls in ('.s-offline', '.s-toast', '.is-loading', '.s-empty', '.s-notice'):
            self.assertIn(cls, css)

    def test_base_loads_script_not_on_vendor(self):
        base = _read(TPL / 'base_shop.html')
        self.assertIn('shop_ux.js', base)
        self.assertIn('/shop/vendor/', base.split('shop_ux.js')[0].rsplit('\n', 1)[-1])
        self.assertIn('shop.css', base)
        self.assertIn('?v=2', base)

    def test_empty_state_used_on_pages(self):
        for page in ('cart.html', 'my_orders.html', 'stores.html', 'favorites.html', 'wallet.html',
                     'repeat_plans.html', 'shop.html', 'store_detail.html'):
            self.assertIn('_empty_state.html', _read(TPL / page), page)


class CustomerStep8TemplatesCompile(SimpleTestCase):
    def test_no_multiline_hash_comments(self):
        # {# #} sirf ek line ka comment hai; do line ka hissa asli tag ban jata hai (500 error)
        bad = []
        for f in TPL.rglob('*.html'):
            for i, line in enumerate(_read(f).split('\n'), 1):
                pos = line.find('{#')
                if pos != -1 and '#}' not in line[pos:]:
                    bad.append((f.name, i))
        self.assertEqual([b for b in bad if b[0] != '_rider_menu.html'], [])

    def test_all_customer_templates_compile(self):
        from django.template import engines
        eng = engines['django']
        for f in sorted(TPL.glob('*.html')):
            eng.get_template('customer_portal/' + f.name)


class CustomerStep8NoAlerts(SimpleTestCase):
    def test_no_alert_in_customer_flow(self):
        for page in ('cart.html', 'checkout.html', 'favorites.html', 'product_detail.html', 'order_detail.html',
                     '_fav_js.html', 'shop.html'):
            self.assertNotRegex(_read(TPL / page), r'(?<![\w.])alert\(', page)

    def test_chat_has_fallback(self):
        s = _read(TPL / '_order_chat_panel.html')
        self.assertIn('window.shopUx', s)

    def test_no_roman_urdu_left_in_js_messages(self):
        for page in ('product_detail.html', 'shop.html'):
            s = _read(TPL / page)
            for bad in ('Pehle ', 'ziyada se ziyada', 'dobara koshish karein', 'nahi hui'):
                self.assertNotIn(bad, s, page)


class CustomerStep10RomanUrdu(SimpleTestCase):
    def test_visible_text_is_english(self):
        for f, bad in (('auth/login.html', 'bhool gaye'), ('product_detail.html', 'pyaaz'), ('checkout.html', 'Jaldi se jaldi'),
                       ('checkout.html', 'ke liye schedule hoga'), ('order_detail.html', 'waqt khatam')):
            self.assertNotIn(bad, _read(TPL / f), f)


class CustomerStep8Checkout(SimpleTestCase):
    def test_double_order_guard(self):
        s = _read(TPL / 'checkout.html')
        self.assertIn('ORDER_IN_FLIGHT', s)
        self.assertIn('shopUx.fetchJson', s)
        self.assertIn('d.success === false', s)
        self.assertIn('window.shopUx.text.unsure', s)

    def test_odd_t_tag_fixed(self):
        self.assertNotIn('{% t "Confirm order</h5>" %}', _read(TPL / 'checkout.html'))


class CustomerStep8Urdu(SimpleTestCase):
    def test_empty_texts_have_urdu(self):
        from app.i18n.customer_step7 import CUSTOMER_DEFAULTS
        from app.i18n.i18n_default import DEFAULTS
        known = {en.strip().lower().rstrip(' .!?') for en, _ in list(CUSTOMER_DEFAULTS) + list(DEFAULTS)}
        missing = []
        for f in sorted(TPL.glob('*.html')):
            for m in INCLUDE.finditer(_read(f)):
                for _k, val in STR_ARG.findall(m.group(1)):
                    if val.strip().lower().rstrip(' .!?') not in known:
                        missing.append((f.name, val))
        self.assertEqual(missing, [])

    def test_tag_texts_have_matching_placeholders(self):
        from app.i18n.customer_step7 import CUSTOMER_TAG
        for en, ur in CUSTOMER_TAG:
            if "<a href='{}'" in en:
                continue
            self.assertEqual(en.count('{}'), ur.count('{}'), en)
