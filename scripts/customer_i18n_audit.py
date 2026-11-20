"""Customer pages mein woh text dhoondta hai jis ka Urdu tarjuma nahi, ya jo Roman Urdu hai, ya jahan
{% if LANG_CODE == 'ur' %}...{% else %}...{% endif %} wali purani nakal baqi hai (Step 7 ka hisab).

Chalane ka tareeqa (project folder se):   python3 scripts/customer_i18n_audit.py [file.html ...]
Koi file na do to customer ke sab templates dekhe jate hain (rider / vendor nahi). Django ki zaroorat nahi.
"""
import glob
import importlib.util
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CUSTOMER_DIR = os.path.join(ROOT, 'templates', 'customer_portal')

_spec = importlib.util.spec_from_file_location('rider_i18n_audit', os.path.join(ROOT, 'scripts', 'rider_i18n_audit.py'))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

ROMAN_URDU = re.compile(
    r'\b(hai|hain|mein|nahi|nahin|aapka|aapki|apna|apni|karein|chunein|badlein|likhein|shukriya|abhi|naya|dena|'
    r'ada|mila|dost|dobara|lena|kuch|masla|maal|koshish|bhejein|dekhein|khatam|wapas|zaroor|bhool|gaye|jaldi|daalein|waqt|jaise)\b', re.I)
LANG_IF = re.compile(r"\{%\s*if\s+LANG_CODE\s*==\s*['\"]ur['\"]\s*%\}")


def customer_files():
    out = []
    for f in sorted(glob.glob(os.path.join(CUSTOMER_DIR, '**', '*.html'), recursive=True)):
        rel = os.path.relpath(f, CUSTOMER_DIR).replace(os.sep, '/')
        if rel.startswith(('rider/', 'vendor/')):
            continue
        out.append(f)
    return out


def roman_urdu(src):
    """Dikhne wale text / {% t %} jumlon mein Roman Urdu lafz."""
    hits = [t for t in base.tag_texts(src) if ROMAN_URDU.search(t)]
    for n in base.text_nodes(src):
        if ROMAN_URDU.search(n) and n not in hits:
            hits.append(n)
    return hits


def lang_ifs(src):
    """Purani nakal: {% if LANG_CODE == 'ur' %} ki ginti."""
    return len(LANG_IF.findall(src))


def untranslated(src, keys):
    miss = [t for t in base.tag_texts(src) if base.core(t) not in keys]
    for n in base.text_nodes(src):
        c = base.core(n)
        if not re.search(r'[A-Za-z]{2}', c) or re.fullmatch(r'[x0-9 +\-]+', c) or c in keys:
            continue
        if n not in miss:
            miss.append(n)
    return miss


def main(files):
    keys = base.known_keys()
    files = files or customer_files()
    tot_miss = tot_roman = tot_if = 0
    for f in files:
        src = open(f, encoding='utf-8').read()
        miss, roman, ifs = untranslated(src, keys), roman_urdu(src), lang_ifs(src)
        tot_miss, tot_roman, tot_if = tot_miss + len(miss), tot_roman + len(roman), tot_if + ifs
        if not (miss or roman or ifs):
            continue
        print('## %s: tarjuma baqi %d | Roman Urdu %d | purani LANG_CODE nakal %d' % (os.path.relpath(f, CUSTOMER_DIR), len(miss), len(roman), ifs))
        for n in roman:
            print('   [Roman Urdu]', n)
        for n in miss:
            print('   -', n)
    print('\nKul: tarjuma baqi %d | Roman Urdu %d | purani LANG_CODE nakal %d' % (tot_miss, tot_roman, tot_if))
    return tot_miss, tot_roman, tot_if


if __name__ == '__main__':
    main(sys.argv[1:])
