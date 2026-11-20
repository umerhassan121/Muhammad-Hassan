"""Customer portal Step 8: static/js/shop_ux.js ko Chromium (phone ki screen 360x640) mein chala kar dekhna.

Kya dekhta hai
  1. form par 3 baar click -> sirf 1 POST, button par spinner (.is-loading)
  2. internet band: laal patti aati hai, normal flow mein hai (header ko dhaanpti nahi), form / link browser ke error page par nahi jate, toast aata hai
  3. internet wapas: patti hat jati hai
  4. toast neeche ki bar (.sm-bar) ke ooper dikhta hai
  5. shopUx.fetchJson: ok / offline / timeout / session(401) / server(500) / html / 404 sahi pehchane jate hain
  6. Urdu (lang=ur) mein patti ka text Urdu hai
  7. page par koi JS error nahi

Chalane ka tareeqa (project folder se):   python3 scripts/checks_and_tests/customer_step8_ux_check.py [--json FILE]
Zaroorat: python3, playwright (chromium). Ye sirf dekhne wala tool hai, project ke code ko nahi badalta.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JS = os.path.join(ROOT, 'static', 'js', 'shop_ux.js')
CSS = os.path.join(ROOT, 'static', 'css', 'shop.css')

PAGE = """<!doctype html><html lang="%(lang)s"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><style>%(css)s body{margin:0;font-family:sans-serif}</style></head>
<body class="has-shop-bar"><header id="hdr" style="height:56px;background:#eee">Header</header>
<iframe name="ifr" style="display:none"></iframe><form id="f" method="post" action="/post" target="ifr"><button id="go" type="submit">Go</button></form>
<a id="lnk" href="/other">Other</a>
<nav class="sm-bar" id="bar"><span>Home</span></nav>
<script>%(js)s</script></body></html>"""


def run(shots_json=None):
    from playwright.sync_api import sync_playwright
    css = open(CSS, encoding='utf-8').read()
    js = open(JS, encoding='utf-8').read()
    results = []

    def check(name, ok, detail=''):
        results.append({'check': name, 'ok': bool(ok), 'detail': detail})
        print(('PASS ' if ok else 'FAIL ') + name + (' - ' + str(detail) if detail else ''))

    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={'width': 360, 'height': 640}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        errors, posts = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))

        def handler(route):
            req = route.request
            u = req.url
            if u.endswith('/post'):
                posts.append(u)
                return   # server dheere jawab de raha hai: page wahin rehta hai, button ka haal dekh sakte hain
            elif u.endswith('/page'):
                route.fulfill(status=200, content_type='text/html', body=PAGE % {'lang': 'en', 'css': css, 'js': js})
            elif u.endswith('/api/ok'):
                route.fulfill(status=200, content_type='application/json', body='{"success": true}')
            elif u.endswith('/api/401'):
                route.fulfill(status=401, content_type='application/json', body='{}')
            elif u.endswith('/api/500'):
                route.fulfill(status=500, content_type='text/html', body='boom')
            elif u.endswith('/api/html'):
                route.fulfill(status=200, content_type='text/html', body='<html></html>')
            elif u.endswith('/api/404'):
                route.fulfill(status=404, content_type='text/html', body='nf')
            elif u.endswith('/api/hang'):
                return   # jawab nahi: timeout ka test
            elif u.endswith('/other'):
                route.fulfill(status=200, content_type='text/html', body='<html>other</html>')
            else:
                route.fulfill(status=200, content_type='text/html', body='')

        ctx.route('**/*', handler)
        page.goto('http://t.local/page')
        # 1. teen baar click -> sirf 1 POST + spinner
        page.goto('http://t.local/page')
        page.click('#go', no_wait_after=True)
        for _ in range(2):
            page.evaluate("document.getElementById('go').dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}))")
        page.wait_for_timeout(300)
        check('3 baar click par sirf 1 POST', len(posts) == 1, len(posts))
        cls = page.evaluate("document.getElementById('go').className")
        check('submit par spinner (.is-loading)', 'is-loading' in cls, cls)
        check('button band ho gaya', page.evaluate("document.getElementById('go') ? document.getElementById('go').disabled : true"))
        # 2/3. offline
        page.goto('http://t.local/page')
        ctx.set_offline(True)
        page.wait_for_timeout(200)
        vis = page.evaluate("getComputedStyle(document.querySelector('.s-offline')).display")
        check('offline: laal patti dikhi', vis == 'block', vis)
        pos = page.evaluate("getComputedStyle(document.querySelector('.s-offline')).position")
        hdr_top = page.evaluate("document.getElementById('hdr').getBoundingClientRect().top")
        bar_h = page.evaluate("document.querySelector('.s-offline').getBoundingClientRect().height")
        check('offline patti normal flow mein (fixed nahi)', pos == 'static', pos)
        check('offline patti header ko nahi dhaanpti', hdr_top >= bar_h - 1, 'header top=%s patti=%s' % (hdr_top, bar_h))
        page.click('#lnk', no_wait_after=True)
        page.wait_for_timeout(200)
        check('offline: link browser error page par nahi gaya', page.url.endswith('/page'), page.url)
        check('offline: toast aaya', page.evaluate("document.querySelector('.s-toast').classList.contains('is-on')"))
        tb = page.evaluate("document.querySelector('.s-toast').getBoundingClientRect().bottom")
        sb = page.evaluate("document.getElementById('bar').getBoundingClientRect().top")
        check('toast neeche ki bar ke ooper', tb <= sb + 1 or sb >= 640, 'toast bottom=%s bar top=%s' % (tb, sb))
        before = len(posts)
        page.evaluate("document.getElementById('f').requestSubmit()")
        page.wait_for_timeout(200)
        check('offline: form nahi gaya', len(posts) == before and page.url.endswith('/page'), page.url)
        k = page.evaluate("shopUx.fetchJson('/api/ok').then(function(r){return r.kind;})")
        check('fetchJson offline', k == 'offline', k)
        ctx.set_offline(False)
        page.wait_for_timeout(200)
        vis = page.evaluate("getComputedStyle(document.querySelector('.s-offline')).display")
        check('online wapas: patti hat gayi', vis == 'none', vis)
        # 5. fetchJson kinds
        for path, want, unsure in (('/api/ok', 'ok', False), ('/api/401', 'session', False), ('/api/500', 'server', True),
                                   ('/api/html', 'html', True), ('/api/404', 'notfound', False)):
            r = page.evaluate("shopUx.fetchJson('%s').then(function(r){return [r.kind, r.unsure];})" % path)
            check('fetchJson %s -> %s' % (path, want), r[0] == want and r[1] == unsure, r)
        r = page.evaluate("shopUx.fetchJson('/api/hang', {}, 400).then(function(r){return [r.kind, r.unsure];})")
        check('fetchJson timeout (shayad chala gaya = unsure)', r[0] == 'timeout' and r[1] is True, r)
        # 6. Urdu
        page = ctx.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.set_content(PAGE % {'lang': 'ur', 'css': css, 'js': js})
        page.wait_for_timeout(100)
        t = page.evaluate("shopUx.text.offline")
        check('Urdu mein patti ka text', any('\u0600' <= c <= '\u06ff' for c in t), t)
        check('page par JS error nahi', not errors, errors)
        b.close()
    if shots_json:
        with open(shots_json, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    bad = [r for r in results if not r['ok']]
    print('\n%d check, %d fail' % (len(results), len(bad)))
    return 1 if bad else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--json')
    a = ap.parse_args()
    sys.exit(run(a.json))
