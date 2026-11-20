"""Vendor style (Step 4): jo `v-` classes templates mein hain, woh vendor.css mein maujood hon; purana mel khatam."""
import re
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
CSS = ROOT / 'static' / 'css' / 'vendor.css'
PAGES = [
    ROOT / 'templates' / 'customer_portal' / 'vendor' / 'promote.html',
    ROOT / 'app' / 'templates' / 'customer_portal' / 'vendor' / '_ads_report.html',
]


def _defined():
    return set(re.findall(r'\.(v-[a-z0-9-]+)', CSS.read_text(encoding='utf-8')))


def _used(path):
    text = path.read_text(encoding='utf-8')
    used = set()
    for attr in re.findall(r'class="([^"]*)"', text):
        attr = re.sub(r'{%.*?%}|{{.*?}}', ' ', attr)          # template tags hatao
        used |= {c for c in attr.split() if c.startswith('v-')}
    return used


class VendorCssTests(SimpleTestCase):
    def test_css_file_exists_and_has_tokens(self):
        text = CSS.read_text(encoding='utf-8')
        for token in ('--v-primary', '--v-radius', '--v-shadow'):
            self.assertIn(token, text)

    def test_every_used_class_is_defined(self):
        defined = _defined()
        for page in PAGES:
            missing = _used(page) - defined
            self.assertFalse(missing, '%s: vendor.css mein nahi: %s' % (page.name, sorted(missing)))

    def test_no_old_style_mix_left(self):
        for page in PAGES:
            text = page.read_text(encoding='utf-8')
            self.assertNotIn('vp-', text, page.name)
            for old in ('btn-primary', 'form-control', 'table-responsive', 'card mb-3', 'btn-outline-secondary'):
                self.assertNotIn(old, text, '%s: purani Bootstrap class %s' % (page.name, old))

    def test_css_only_touches_v_classes(self):
        css = re.sub(r'/\*.*?\*/', '', CSS.read_text(encoding='utf-8'), flags=re.S)
        selectors = re.findall(r'(?:^|})\s*([^{}@]+?)\s*{', css)
        for sel in selectors:
            for part in sel.split(','):
                part = part.strip()
                if not part or part == ':root' or part.startswith(('from', 'to')):
                    continue
                self.assertTrue(re.match(r'^\.v-', part), 'vendor.css mein v- ke ilawa selector: %s' % part)

    def test_base_loads_css_only_on_vendor_pages(self):
        base = (ROOT / 'templates' / 'customer_portal' / 'base_shop.html').read_text(encoding='utf-8')
        self.assertIn("css/vendor.css", base)
        self.assertIn('/shop/vendor/', base)
