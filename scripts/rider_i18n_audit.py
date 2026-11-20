"""Rider templates mein woh English text dhoondta hai jis ka Urdu tarjuma (dictionary / {% t %}) nahi hai.

Chalane ka tareeqa (project folder se):   python3 scripts/rider_i18n_audit.py [file.html ...]
Koi file na do to rider ke sab templates dekhe jate hain. Django ki zaroorat nahi.
"""
import glob
import html
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
RIDER_DIR = os.path.join(ROOT, 'templates', 'customer_portal', 'rider')
_LEAD = re.compile(r'^[^\w(]+')
_TAIL = ' :.…!?*'


def core(s):
    s = re.sub(r'\s+', ' ', html.unescape(s)).strip()
    return _LEAD.sub('', s).rstrip(_TAIL).strip().lower()


def known_keys():
    from app.i18n import i18n_default, portal_messages
    keys = {core(k) for k, _ in i18n_default.DEFAULTS}
    keys |= {core(k) for k, _ in portal_messages.CATALOG}
    keys |= {core(k) for k, _ in portal_messages.TAG_ONLY}
    return keys


def text_nodes(src):
    """Template ka dikhne wala text, tukron mein ({% t %} wale tukre alag)."""
    src = re.sub(r'\{#.*?#\}', '', src, flags=re.S)
    src = re.sub(r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}', '', src, flags=re.S)
    src = re.sub(r'<(script|style)\b.*?</\1>', '', src, flags=re.S | re.I)
    src = re.sub(r'\{%\s*t\s+.*?%\}', ' ', src, flags=re.S)     # {% t %} khud tarjuma karta hai
    src = re.sub(r'\{[%{].*?[%}]\}', '\x00', src, flags=re.S)    # baqi tags / variables: tukra todte hain
    out = []
    for chunk in re.split(r'<[^>]*>', src):
        for part in chunk.split('\x00'):
            p = re.sub(r'\s+', ' ', part).strip()
            if p:
                out.append(p)
    # placeholder / title / aria-label wagera
    for m in re.finditer(r'\b(?:placeholder|title|aria-label|alt)="([^"{}]+)"', src):
        out.append(m.group(1).strip())
    return out


def tag_texts(src):
    """{% t "..." %} ke andar ke English jumle."""
    return [m.group(1) for m in re.finditer(r'\{%\s*t\s+"((?:[^"\\]|\\.)*)"', src)]


def main(files):
    keys = known_keys()
    files = files or sorted(glob.glob(os.path.join(RIDER_DIR, '*.html')))
    missing_total = 0
    for f in files:
        with open(f, encoding='utf-8') as fh:
            nodes = text_nodes(fh.read())
        miss = [t for t in tag_texts(open(f, encoding='utf-8').read()) if core(t) not in keys]
        for n in nodes:
            c = core(n)
            if not re.search(r'[A-Za-z]{2}', c) or re.fullmatch(r'[x0-9 +\-]+', c) or c in keys:
                continue
            if n not in miss:
                miss.append(n)
        missing_total += len(miss)
        print('## %s: %d tarjuma baqi' % (os.path.basename(f), len(miss)))
        for n in miss:
            print('   -', n)
    print('\nKul baqi: %d' % missing_total)
    return missing_total


if __name__ == '__main__':
    main(sys.argv[1:])
