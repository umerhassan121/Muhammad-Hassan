"""Step 5: har vendor page par shared menu aana chahiye (sab base_shop se extend karein)."""
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
DIRS = [ROOT / 'templates' / 'customer_portal' / 'vendor',
        ROOT / 'app' / 'templates' / 'customer_portal' / 'vendor']
# partials (_*), login/register (menu nahi), print receipt (sirf print)
SKIP = {'login.html', 'register.html', 'order_receipt.html'}


class VendorPagesExtendBase(SimpleTestCase):
    def test_every_vendor_page_extends_base_shop(self):
        bad = []
        for d in DIRS:
            for f in sorted(d.glob('*.html')):
                if f.name.startswith('_') or f.name in SKIP:
                    continue
                if 'extends' not in f.read_text(encoding='utf-8')[:200]:
                    bad.append(f.name)
        self.assertEqual(bad, [], 'In pages par vendor menu nahi aayega: %s' % bad)
