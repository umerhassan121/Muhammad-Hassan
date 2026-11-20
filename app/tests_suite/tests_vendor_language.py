"""Step 6: vendor pages mein Roman Urdu nahi - text English hota hai, Urdu translation se aati hai."""
import re
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
DIRS = [ROOT / 'templates' / 'customer_portal' / 'vendor', ROOT / 'app' / 'templates' / 'customer_portal' / 'vendor']
ROMAN = re.compile(
    r'\b(nahi|nahin|karein|karen|chunein|chunen|abhi|dobara|likhein|likhen|kholein|kholen|badlein|tayyar|kitne|kitna|'
    r'bhejein|bhejen|chahiye|rakhein|dekhein|zaroori|masla|jawab|aapka|aapki|aapke|apna|apni|apne|maujood|mojood|'
    r'koshish|qubool|kar diya|ho gaya|ho gayi|dabayen|banayen|zyada se zyada|kam az kam)\b', re.I)


def _visible(text):
    t = re.sub(r'\{#.*?#\}', '', text, flags=re.S)
    t = re.sub(r'\{[%{].*?[%}]\}', ' ', t, flags=re.S)
    t = re.sub(r'<style.*?</style>', '', t, flags=re.S)
    t = re.sub(r'(?m)^\s*(//|/\*).*$', '', t)          # JS / CSS comments
    t = re.sub(r'<[^>]+>', ' ', t)
    return t


class VendorTemplatesAreEnglish(SimpleTestCase):
    def test_no_roman_urdu_in_vendor_templates(self):
        hits = []
        for d in DIRS:
            for f in sorted(d.glob('*.html')):
                for i, line in enumerate(_visible(f.read_text(encoding='utf-8')).split('\n'), 1):
                    if ROMAN.search(line) and '//' not in line:
                        hits.append('%s:%d %s' % (f.name, i, line.strip()[:80]))
        self.assertEqual(hits, [], 'Roman Urdu mila:\n' + '\n'.join(hits))


class VendorUrduCatalog(SimpleTestCase):
    def test_placeholders_match(self):
        from app.i18n import vendor_step6 as v
        for name in ('VENDOR_TAG', 'VENDOR_CATALOG'):
            for en, ur in getattr(v, name):
                self.assertEqual(en.count('{}'), ur.count('{}'), '{} count alag hai: %s' % en)
