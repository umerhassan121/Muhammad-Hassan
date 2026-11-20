"""Customer portal Step 9: phone par test (asal phone ke baghair, Chromium mein 320 / 360 / 390 px, English aur Urdu).

Asal templates (_shop_menu.html, _empty_state.html) ko Jinja se render karta hai (Django ki zaroorat nahi), shop.css laga kar naapta hai:
  1. har button / link kam az kam 44px (neeche ki bar ke tab, khali screen ke button, wajah wali patti ke button)
  2. page par aadhi screen se bahar nikalne wala (horizontal scroll) nahi
  3. neeche ki bar aur chipakne wali patti (.pd-bar) takrate nahi; toast bar ke ooper hai
  4. internet ki patti header ko nahi dhaanpti
  5. Urdu (RTL) mein bar ke labels kat te nahi
Chalane ka tareeqa:  python3 scripts/checks_and_tests/customer_step9_phone_check.py [--json FILE]
Zaroorat: python3, jinja2, playwright (chromium). Natija asal phone ka badal nahi: notch, back button, APK, push phone par dekhna hota hai.
"""
import argparse
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
_spec = importlib.util.spec_from_file_location('rider_check', os.path.join(ROOT, 'scripts', 'checks_and_tests', 'rider_step8_phone_check.py'))
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

EMPTIES = [
    ("bi-cart-x", "Your cart is empty", "Add your favourite products and order with Cash on Delivery.", "Start shopping", ""),
    ("bi-box-seam", "No Orders Found", "There are no orders in this status", "Show all orders", "Start Shopping"),
    ("bi-shop", "No stores found", "Try another search or clear the filters.", "Clear filters", ""),
]


def build(lang):
    env = rc.make_env(lang)
    from app.i18n import customer_step7 as c7
    ur = dict(c7.CUSTOMER_DEFAULTS)
    ur.update(dict(c7.CUSTOMER_TAG))
    tr = (lambda s: ur.get(s, s)) if lang == 'ur' else (lambda s: s)
    tabs = [dict(url='/s/home', label=tr('Home'), icon='bi-house', icon_on='bi-house-fill', active=True, is_cart=False, is_account=False, badge=0),
            dict(url='/s/stores', label=tr('Stores'), icon='bi-shop', icon_on='bi-shop', active=False, is_cart=False, is_account=False, badge=0),
            dict(url='/s/cart', label=tr('Cart'), icon='bi-cart3', icon_on='bi-cart3', active=False, is_cart=True, is_account=False, badge=2),
            dict(url='/s/orders', label=tr('Orders'), icon='bi-bag', icon_on='bi-bag-fill', active=False, is_cart=False, is_account=False, badge=1),
            dict(url='/s/account', label=tr('Account'), icon='bi-person', icon_on='bi-person-fill', active=False, is_cart=False, is_account=True, badge=0)]
    ctx = rc.context(lang, sm_tabs=tabs, sm_show_bar=True, sm_logged_in=True)
    menu = env.get_template('customer_portal/_shop_menu.html').render(**ctx)
    empties = ''.join(env.get_template('customer_portal/_empty_state.html').render(
        icon=i, title=tr(t), text=tr(x), cta_url='/x', cta_label=tr(c), cta2_url='/y' if c2 else '', cta2_label=tr(c2), **ctx)
        for i, t, x, c, c2 in EMPTIES)
    css = open(os.path.join(ROOT, 'static', 'css', 'shop.css'), encoding='utf-8').read()
    js = open(os.path.join(ROOT, 'static', 'js', 'shop_ux.js'), encoding='utf-8').read()
    return ('<!doctype html><html lang="%s" dir="%s"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<style>%s body{margin:0;font-family:sans-serif} .pd-bar{position:fixed;left:0;right:0;bottom:0;height:60px;background:#ddd}</style></head><body class="has-shop-menu has-shop-bar">'
            '<header id="hdr" style="height:56px;background:#eee">Header</header>%s'
            '<div class="s-notice s-notice--bad" id="ntc"><i class="bi"></i><div class="s-notice__body"><div>Order not confirmed</div>'
            '<div class="s-notice__actions"><a href="/o">My Orders</a><a href="/c">Back to cart</a><button type="button">Try again</button></div></div></div>'
            '<div class="pd-bar" id="pd">Add to cart</div>'
            '%s<script>%s</script></body></html>') % (lang, 'rtl' if lang == 'ur' else 'ltr', css, empties, menu, js)


def run(out=None):
    from playwright.sync_api import sync_playwright
    res = []

    def check(name, ok, detail=''):
        res.append({'check': name, 'ok': bool(ok), 'detail': detail})
        print(('PASS ' if ok else 'FAIL ') + name + (' - ' + str(detail) if detail else ''))

    with sync_playwright() as p:
        b = p.chromium.launch()
        for lang in ('en', 'ur'):
            html = build(lang)
            for w, h in ((320, 640), (360, 640), (390, 844)):
                tag = '%s %dpx' % (lang, w)
                ctx = b.new_context(viewport={'width': w, 'height': h}, is_mobile=True, has_touch=True)
                pg = ctx.new_page()
                errs = []
                pg.on('pageerror', lambda e: errs.append(str(e)))
                pg.set_content(html)
                pg.wait_for_timeout(150)
                small = pg.evaluate("""() => Array.from(document.querySelectorAll('.sm-tab, .s-empty__cta, .s-notice__actions a, .s-notice__actions button'))
                    .filter(e => e.getBoundingClientRect().width > 0).map(e => [e.className.split(' ')[0] + ':' + e.textContent.trim().slice(0, 14),
                    Math.round(e.getBoundingClientRect().width), Math.round(e.getBoundingClientRect().height)]).filter(x => x[2] < 44 || x[1] < 44)""")
                check(tag + ': har button 44px ya zyada', not small, small)
                ov = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                check(tag + ': horizontal scroll nahi', ov <= 0, ov)
                cut = pg.evaluate("Array.from(document.querySelectorAll('.sm-lbl')).filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.textContent)")
                check(tag + ': bar ke labels kat te nahi', not cut, cut)
                bar = pg.evaluate("document.getElementById('smBar').getBoundingClientRect().top")
                pd = pg.evaluate("(function(){var e=document.getElementById('pd');var s=getComputedStyle(e);return e.getBoundingClientRect().bottom;})()")
                check(tag + ': chipakne wali patti bar ke ooper (shop.css rule)', pd <= bar + 1, 'patti bottom=%s bar top=%s' % (pd, bar))
                pg.evaluate("shopUx.error('Test toast')")
                pg.wait_for_timeout(300)
                tb = pg.evaluate("document.querySelector('.s-toast').getBoundingClientRect().bottom")
                check(tag + ': toast bar ke ooper', tb <= bar + 1, 'toast bottom=%s bar top=%s' % (tb, bar))
                pg.evaluate("window.dispatchEvent(new Event('offline'))")
                pg.wait_for_timeout(100)
                ht = pg.evaluate("document.getElementById('hdr').getBoundingClientRect().top")
                bh = pg.evaluate("document.querySelector('.s-offline').getBoundingClientRect().height")
                check(tag + ': internet patti header ko nahi dhaanpti', ht >= bh - 1, 'header top=%s patti=%s' % (ht, bh))
                check(tag + ': JS error nahi', not errs, errs)
                ctx.close()
        b.close()
    if out:
        json.dump(res, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    bad = [r for r in res if not r['ok']]
    print('\n%d check, %d fail' % (len(res), len(bad)))
    return 1 if bad else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--json')
    sys.exit(run(ap.parse_args().json))
