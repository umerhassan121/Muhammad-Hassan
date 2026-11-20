"""Step 7: khali / loading / error screens - har empty-state ka text English + Urdu mein maujood ho."""
import re
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / 'templates' / 'customer_portal' / 'vendor'
APP_VENDOR = ROOT / 'app' / 'templates' / 'customer_portal' / 'vendor'
INCLUDE = re.compile(r"\{% include 'customer_portal/vendor/_vendor_empty\.html' with (.*?) %\}", re.S)
STR_ARG = re.compile(r"\b(title|text|cta_label)='([^']*)'")


def _empty_texts():
    out = []
    for d in (VENDOR, APP_VENDOR):
        for f in sorted(d.glob('*.html')):
            for m in INCLUDE.finditer(f.read_text(encoding='utf-8')):
                for key, val in STR_ARG.findall(m.group(1)):
                    out.append((f.name, key, val))
    return out


class VendorEmptyStates(SimpleTestCase):
    def test_partial_and_assets_exist(self):
        self.assertTrue((APP_VENDOR / '_vendor_empty.html').exists())
        self.assertTrue((ROOT / 'static' / 'js' / 'vendor_ux.js').exists())
        nav = (APP_VENDOR / '_vendor_nav.html').read_text(encoding='utf-8')
        self.assertIn('vendor_ux.js', nav)
        css = (ROOT / 'static' / 'css' / 'vendor.css').read_text(encoding='utf-8')
        for cls in ('.v-empty-state', '.is-loading', '.v-offline', '.v-toast'):
            self.assertIn(cls, css)

    def test_empty_states_are_used(self):
        used = {f for f, _k, _v in _empty_texts()}
        for page in ('orders.html', 'menu.html', 'dashboard.html', 'reports.html'):
            self.assertIn(page, used, '%s mein khali screen nahi lagi' % page)

    def test_every_empty_text_has_urdu(self):
        from app.i18n.vendor_step6 import VENDOR_DEFAULTS
        have = {en for en, _ur in VENDOR_DEFAULTS}
        missing = sorted({'%s: %s' % (f, v) for f, _k, v in _empty_texts() if v not in have})
        self.assertEqual(missing, [], 'Urdu translation nahi mili:\n' + '\n'.join(missing))

    def test_no_roman_urdu_error_in_product_forms(self):
        for name in ('product_form.html', 'product_bulk_form.html'):
            self.assertNotIn('Error aa gaya', (VENDOR / name).read_text(encoding='utf-8'))


class VendorPhoneFixes(SimpleTestCase):
    def test_ringer_on_every_vendor_page_without_double_start(self):
        nav = (APP_VENDOR / '_vendor_nav.html').read_text(encoding='utf-8')
        self.assertIn('_order_ringer.html', nav)
        ringer = (VENDOR / '_order_ringer.html').read_text(encoding='utf-8')
        self.assertIn('window.__voRinger', ringer)

    def test_touch_targets_and_input_font_css(self):
        css = (ROOT / 'static' / 'css' / 'vendor.css').read_text(encoding='utf-8')
        for cls in ('.br-mini', '.dl-end', '.vm-btn', '.vo2-mini', '.po-mini', '.st-mini', '.vst-btn'):
            self.assertIn(cls, css)
        self.assertIn('min-height: 44px', css)
        self.assertIn('font-size: 16px !important', css)
