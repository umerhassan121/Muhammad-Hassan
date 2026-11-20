"""Rider portal Step 8 (Step 9 ke baad dobara chalane ke liye): phone par test (asal phone ke baghair, Chromium mein phone ki screen size par).

Kya karta hai
  Rider ke asal templates (base.html, _rider_menu.html, home.html, _order_card.html ...) ko Jinja se render karta hai
  (Django ki zaroorat nahi), phir Chromium (Playwright) mein 320 / 360 / 390 px wali screen par kholta hai aur naapta hai:
    1. har button / link / input kam az kam 44px hai ya nahi
    2. neeche ki bar, SOS button, location ki patti, "More" sheet aapas mein takrate to nahi
    3. internet / GPS ki patti upar ke Online switch ko dhaank to nahi rahi
    4. naye order ka popup: ACCEPT button bina scroll ke nazar aata hai ya nahi
    5. Urdu mein neeche ki bar ke labels kat to nahi rahe
    6. (Step 9 ke guard) likha hua reload se nahi mitta, back button sheet band karta hai, popup offline mein error page nahi kholta

Chalane ka tareeqa (project folder se):
    python3 scripts/checks_and_tests/rider_step8_phone_check.py [--shots DIR] [--json FILE]

Zaroorat: python3, jinja2, playwright (chromium). Ye sirf dekhne wala tool hai, project ke code ko nahi badalta.
Nateeja asal phone ka badal nahi hai: awaaz, background GPS, APK ka back button phone par hi dekhna hota hai.
"""
import argparse
import html as _html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TPL = os.path.join(ROOT, 'templates')
STATIC = os.path.join(ROOT, 'static')
sys.path.insert(0, ROOT)

import jinja2  # noqa: E402

# ---------------------------------------------------------------- Django -> Jinja
_STUB = {'pwa/_pwa.html', 'customer_portal/_native_push.html', 'customer_portal/_push_prompt.html',
         'customer_portal/_order_chat_panel.html'}


def _expr(e):
    e = re.sub(r'\|(\w+):("[^"]*"|\'[^\']*\'|[\w.\-]+)', r'|\1(\2)', e)
    e = e.replace('forloop.', 'loop.')
    e = re.sub(r'\bis not None\b', 'is not none', e)
    return e


def _split_args(s):
    out, cur, q = [], '', None
    for ch in s.strip():
        if q:
            cur += ch
            if ch == q:
                q = None
        elif ch in '"\'':
            q = ch
            cur += ch
        elif ch.isspace():
            if cur:
                out.append(cur)
                cur = ''
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def convert(src):
    src = re.sub(r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}', '', src, flags=re.S)
    src = re.sub(r'\{%\s*load [^%]*%\}', '', src)
    src = re.sub(r'\{%\s*verbatim\s*%\}', '{% raw %}', src)
    src = re.sub(r'\{%\s*endverbatim\s*%\}', '{% endraw %}', src)
    src = re.sub(r'\{%\s*static\s+[\'"]([^\'"]+)[\'"]\s*%\}', r'/static/\1', src)
    src = re.sub(r'\{%\s*csrf_token\s*%\}', '<input type="hidden" name="csrfmiddlewaretoken" value="x">', src)

    def url(m):
        parts = _split_args(m.group(1))
        return '{{ url(%s) }}' % ', '.join(_expr(p) for p in parts)
    src = re.sub(r'\{%\s*url\s+([^%]*?)\s*%\}', url, src)

    def tt(m):
        parts = _split_args(m.group(1))
        return '{{ t(%s) }}' % ', '.join(_expr(p) for p in parts)
    src = re.sub(r'\{%\s*t\s+([^%]*?)\s*%\}', tt, src)

    def inc(m):
        name, rest = m.group(1), (m.group(2) or '').strip()
        if not rest:
            return "{%% include '%s' %%}" % name
        kv = re.findall(r'(\w+)=("[^"]*"|\'[^\']*\'|[\w.]+)', rest)
        return "{%% with %s %%}{%% include '%s' %%}{%% endwith %%}" % (', '.join('%s=%s' % (k, _expr(v)) for k, v in kv), name)
    src = re.sub(r'\{%\s*include\s+[\'"]([^\'"]+)[\'"]\s*(?:with\s+([^%]*?))?\s*%\}', inc, src)
    src = re.sub(r'\{%\s*empty\s*%\}', '{% else %}', src)
    src = re.sub(r'\{%\s*extends\s+[\'"]([^\'"]+)[\'"]\s*%\}', r"{% extends '\1' %}", src)

    def tag(m):
        body = m.group(1).strip()
        if body.split(None, 1)[0] in ('block', 'endblock', 'extends', 'include', 'endif', 'else', 'endfor', 'endwith', 'raw', 'endraw'):
            return m.group(0)
        return '{%% %s %%}' % _expr(body)
    src = re.sub(r'\{%(.*?)%\}', tag, src, flags=re.S)
    src = re.sub(r'\{\{(.*?)\}\}', lambda m: '{{ %s }}' % _expr(m.group(1).strip()), src, flags=re.S)
    return src


class Loader(jinja2.BaseLoader):
    def get_source(self, env, name):
        if name in _STUB:
            return '', name, lambda: True
        p = os.path.join(TPL, name)
        if not os.path.exists(p):
            raise jinja2.TemplateNotFound(name)
        with open(p, encoding='utf-8') as fh:
            return convert(fh.read()), p, lambda: True


class AllOn:
    """SHOP.<koi bhi flag> = True (sab features on: sab se zyada buttons / tab dikhte hain)."""
    def __getattr__(self, k):
        return True


class Card(dict):
    @property
    def items(self):
        return self['items']


def make_env(lang):
    from app.i18n import portal_messages, rider_step6
    cat = {}
    for k, v in list(portal_messages.CATALOG) + list(portal_messages.TAG_ONLY) + list(rider_step6.RIDER_TAG):
        cat[k] = v

    def t(msg, *a):
        out = cat.get(msg, msg) if lang == 'ur' else msg
        for x in a:
            out = out.replace('{}', str(x), 1)
        return out

    def floatformat(v, d=1):
        try:
            d = int(d)
            f = float(v)
            return ('%.' + str(abs(d)) + 'f') % f if d > 0 or f % 1 else '%d' % f
        except Exception:
            return ''

    env = jinja2.Environment(loader=Loader(), autoescape=False, undefined=jinja2.ChainableUndefined)
    env.globals['url'] = lambda name, *a: '/u/%s/%s' % (name, '/'.join(str(x) for x in a) + ('/' if a else ''))
    env.globals['t'] = t
    env.filters.update(floatformat=floatformat, date=lambda v, f='': str(v), time=lambda v, f='': str(v),
                       urlencode=lambda v: str(v))
    return env


def order_card(st, arrived=False, n=1):
    return Card(order=Card(id=100 + n, order_no=2040 + n, customer=Card(name='Ahmed Raza')), di=Card(status=st, arrived_store_at=None, arrived_customer_at='12:10' if arrived else None),
                store='Karachi Biryani House', store_addr='Shop 4, Block 7, Gulshan', cust_addr='House 12, Street 5, Clifton',
                is_cod=True, total=1850, items=[Card(qty=2, product=Card(name='Chicken Biryani')), Card(qty=1, product=Card(name='Raita'))],
                store_issue=None, fail=None, fail_left=0, fail_min=0, store_phone='0300', cust_phone='0311', wa_cust='https://wa.me/1',
                map_store='https://maps/1', map_pin='https://maps/2', map_cust='https://maps/3', nav_inapp=True,
                nav=Card(google='https://maps/g', waze='https://waze/w'), issue_reasons=[('closed', 'Store closed'), ('other', 'Other')],
                fail_reasons=[('no_answer', 'Customer not answering'), ('other', 'Other')])


def context(lang, **kw):
    ctx = dict(
        LANG_CODE=lang, LANG_DIR='rtl' if lang == 'ur' else 'ltr', company_name='Demo Co', company_logo='',
        LANGUAGES=[Card(code='en', native='English'), Card(code='ur', native='اردو')],
        request=Card(get_full_path='/shop/rider/'), csrf_token='x', messages=[],
        SHOP=AllOn(), rider=Card(name='Umer Shahzad', is_online=True, approval_status='approved'),
        nav='orders', badge_count=3, active_count=1, support_unread=2, more_badge=3, dispute_count=1, doc_warn_n=2,
        today=Card(deliveries=7, earned=1260), cash=Card(level='warn', cash=4200, limit=5000), balances=Card(cash_in_hand=4200),
        gate_msg='', doc_warnings=['Your CNIC expires in 5 days'], next_shift=None, peak_now=None, plan=None,
        mine=[order_card('assigned', n=1), order_card('picked', arrived=True, n=2)], max_active=3,
        offers=[Card(order=Card(id=7, order_no=2051), fee=180, peak=0, batch='', store='Karachi Biryani House', store_addr='Shop 4', cust_addr='House 12, Clifton',
                     items_count=3, dist_km=2.1, is_cod=True, total=1850)],
        goal_list=[], unassign_reasons=[('sick', 'I am unwell'), ('bike', 'Bike problem')], I18N_VERSION='1')
    ctx.update(kw)
    return ctx


def render_home(lang='en', **kw):
    env = make_env(lang)
    return env.get_template('customer_portal/rider/home.html').render(**context(lang, **kw))


def ur_dictionary():
    from app.i18n import i18n_default, portal_messages, rider_step6
    d = {}
    for src in (i18n_default.DEFAULTS, portal_messages.CATALOG, rider_step6.RIDER_DEFAULTS):
        for k, v in src:
            d[k.strip().lower()] = v
    return 'window.ERP_I18N=' + json.dumps(d, ensure_ascii=False) + ';'


# ---------------------------------------------------------------- Browser
VIEWPORTS = [('small-320x568', 320, 568, 0, 0), ('android-360x640', 360, 640, 0, 0), ('iphone-390x844', 390, 844, 47, 34)]

MEASURE_JS = r"""
() => {
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && !e.closest('[hidden]'); };
  const lab = e => (e.getAttribute('aria-label') || e.innerText || e.value || e.getAttribute('placeholder') || e.name || e.tagName).trim().replace(/\s+/g,' ').slice(0, 40);
  const out = [];
  document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, summary').forEach(e => {
    if (!vis(e)) return;
    if (e.closest('.erp-lang-switch') && e.tagName !== 'A') return;
    const r = e.getBoundingClientRect();
    out.push({tag: e.tagName.toLowerCase() + (e.className ? '.' + String(e.className).split(' ')[0] : ''), label: lab(e), w: Math.round(r.width), h: Math.round(r.height)});
  });
  return out;
}
"""


def run(args):
    from playwright.sync_api import sync_playwright
    report = {'small_targets': {}, 'overlaps': [], 'notes': []}
    html_en = render_home('en')
    html_ur = render_home('ur')
    ur_dict = ur_dictionary()
    poll_offer = {'offers': 1, 'active': 1, 'assigned': 1, 'online': True, 'alert_seconds': 20, 'offer_list': [
        {'id': 7, 'order_no': '2051', 'store': 'Karachi Biryani House', 'store_addr': 'Shop 4, Block 7, Gulshan', 'cust_addr': 'House 12, Street 5, Clifton',
         'fee': '180', 'is_cod': True, 'total': '1,850', 'dist_km': 2.1, 'items': 3, 'accept_url': '/u/rider_accept_order/7/', 'decline_url': '/u/rider_decline_order/7/'}]}
    poll_idle = {'offers': 0, 'active': 1, 'assigned': 1, 'online': True, 'offer_list': [], 'alert_seconds': 20}

    def safe(text, top, bottom):
        text = re.sub(r'env\(safe-area-inset-top[^)]*\)', '%dpx' % top, text)
        return re.sub(r'env\(safe-area-inset-bottom[^)]*\)', '%dpx' % bottom, text)

    def serve(page, doc, top, bottom, poll):
        def h(route):
            u = route.request.url
            path = u.split('//', 1)[1].split('/', 1)[1] if '//' in u else ''
            path = '/' + path.split('?')[0]
            if path == '/shop/rider/':
                return route.fulfill(status=200, content_type='text/html; charset=utf-8', body=safe(doc, top, bottom))
            if path.startswith('/static/'):
                p = os.path.join(STATIC, path[len('/static/'):])
                if os.path.exists(p):
                    body = open(p, 'rb').read()
                    if p.endswith('.css') or p.endswith('.js'):
                        body = safe(body.decode('utf-8'), top, bottom).encode('utf-8')
                    ct = 'text/css' if p.endswith('.css') else 'application/javascript' if p.endswith('.js') else 'font/woff' if p.endswith('.woff') else 'application/octet-stream'
                    return route.fulfill(status=200, content_type=ct, body=body)
            if path.startswith('/u/rider_poll'):
                return route.fulfill(status=200, content_type='application/json', body=json.dumps(poll() if callable(poll) else poll))
            if path.startswith('/u/i18n_dictionary'):
                return route.fulfill(status=200, content_type='application/javascript', body=ur_dict)
            return route.fulfill(status=204, body='')
        page.route('**/*', h)

    shots = args.shots
    if shots:
        os.makedirs(shots, exist_ok=True)

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for name, w, h, top, bottom in VIEWPORTS:
            for lang, doc in (('en', html_en), ('ur', html_ur)):
                ctx = br.new_context(viewport={'width': w, 'height': h}, device_scale_factor=2 if shots else 1, is_mobile=True, has_touch=True, locale='ur-PK' if lang == 'ur' else 'en-US',
                                 permissions=['geolocation'], geolocation={'latitude': 24.86, 'longitude': 67.0})
                ctx.add_init_script("window.__alerts=[];")
                page = ctx.new_page()
                serve(page, doc, top, bottom, poll_idle)
                page.goto('http://t.local/shop/rider/')
                page.wait_for_timeout(700)
                tag = '%s-%s' % (name, lang)

                # 1. chhote buttons
                items = page.evaluate(MEASURE_JS)
                small = [i for i in items if i['h'] < 44 or i['w'] < 44]
                report['small_targets'][tag] = small
                if shots:
                    page.screenshot(path=os.path.join(shots, tag + '-home-top.png'))

                # 2. neeche: SOS, bar, chip
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(200)
                geo = page.evaluate("""() => {
                  const r = s => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return {x: b.x, y: b.y, w: b.width, h: b.height, b: b.bottom, r: b.right}; };
                  const doc = document.documentElement;
                  // aakhri card ka aakhri button bar / SOS ke peeche to nahi
                  const els = Array.from(document.querySelectorAll('.wrap a, .wrap button, .wrap summary')).filter(e => e.getBoundingClientRect().height > 0);
                  const last = els.length ? els[els.length - 1].getBoundingClientRect() : null;
                  return {nav: r('.rnav'), sos: r('.sosfab'), vh: innerHeight, vw: innerWidth, lastBottom: last ? last.bottom : null,
                          sw: doc.scrollWidth, cw: doc.clientWidth, bodyPad: getComputedStyle(document.body).paddingBottom};
                }""")
                tag_geo = geo
                if geo['sw'] > geo['cw'] + 1:
                    report['overlaps'].append('%s: page chaudai se bahar (scrollWidth %s > %s) - side scroll' % (tag, geo['sw'], geo['cw']))
                if geo['nav'] and geo['lastBottom'] and geo['lastBottom'] > geo['nav']['y'] + 0.5:
                    report['overlaps'].append('%s: aakhri button (neeche %.0f) neeche ki bar (shuru %.0f) ke peeche chhup raha hai' % (tag, geo['lastBottom'], geo['nav']['y']))
                if geo['sos'] and geo['nav'] and geo['sos']['b'] > geo['nav']['y'] - 2:
                    report['overlaps'].append('%s: SOS button neeche ki bar se takra raha hai' % tag)
                report.setdefault('geo', {})[tag] = geo
                if shots:
                    page.screenshot(path=os.path.join(shots, tag + '-home-bottom.png'))

                # 3. SOS aur oonchi cheezon par asal "kaun upar hai" (elementFromPoint)
                cover = page.evaluate("""() => {
                  const btn = document.querySelector('.wrap .hb, .wrap .btn');
                  const sos = document.querySelector('.sosfab'); if (!sos) return null;
                  const s = sos.getBoundingClientRect();
                  // SOS ke neeche kaun kaun se tap karne wale elements hain
                  const under = Array.from(document.querySelectorAll('.wrap a, .wrap button, .wrap summary, .wrap input, .wrap select')).filter(e => {
                    if (e.checkVisibility && !e.checkVisibility()) return false;
                    const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0 && b.left < s.right && b.right > s.left && b.top < s.bottom && b.bottom > s.top; })
                    .map(e => (e.innerText || e.name || e.tagName).trim().slice(0, 30));
                  return under;
                }""")
                if cover:
                    report.setdefault('sos_covers', {})[tag] = cover
                # location ki patti (chip) ka asar: _live_location.html jaisi patti bana kar dekhte hain
                chip = page.evaluate(safe("""() => {
                  const c = document.createElement('div');
                  c.style.cssText = 'position:fixed;left:12px;right:72px;bottom:calc(66px + env(safe-area-inset-bottom,0px));background:#111827;color:#fff;border-radius:12px;padding:8px 12px;font-size:12px;font-weight:700;text-align:center;z-index:40';
                  c.textContent = '\\uD83D\\uDCE1 No internet \\u2014 saving location (5). It will be sent automatically when you are back online.';
                  document.body.appendChild(c);
                  const b = c.getBoundingClientRect(); const s = document.querySelector('.sosfab'); const n = document.querySelector('.rnav');
                  const sb = s ? s.getBoundingClientRect() : null; const nb = n.getBoundingClientRect();
                  const res = {chipTop: b.top, chipBottom: b.bottom, navTop: nb.top, sosTop: sb ? sb.top : null, sosBottom: sb ? sb.bottom : null,
                               chipOverlapsSos: sb ? (b.right > sb.left && b.bottom > sb.top && b.top < sb.bottom) : false, chipOverlapsNav: b.bottom > nb.top};
                  c.remove(); return res; }""", top, bottom))
                report.setdefault('chip', {})[tag] = chip

                # More sheet
                page.evaluate("window.scrollTo(0,0)")
                page.click('#rMoreBtn')
                page.wait_for_timeout(350)
                more = page.evaluate("""() => { const m = document.querySelector('#rMore'); const b = m.getBoundingClientRect();
                   const sosTop = document.querySelector('.sosfab'); let top = null;
                   if (sosTop) { const s = sosTop.getBoundingClientRect(); const e = document.elementFromPoint(s.x + s.width/2, s.y + s.height/2); top = e ? (e.className || e.tagName) : null; }
                   const links = Array.from(m.querySelectorAll('a')).map(a => Math.round(a.getBoundingClientRect().height));
                   return {top: b.top, bottom: b.bottom, vh: innerHeight, scrolls: m.scrollHeight > m.clientHeight, sosPoint: top, minLink: Math.min.apply(null, links)}; }""")
                report.setdefault('more', {})[tag] = more
                if shots:
                    page.screenshot(path=os.path.join(shots, tag + '-more.png'))
                page.mouse.click(10, 120)
                page.wait_for_timeout(250)

                # 4. internet / GPS patti Online switch ko dhaankti hai?
                page.evaluate("window.scrollTo(0,0)")
                page.evaluate("riderUx.gps('denied')")
                page.wait_for_timeout(100)
                cov = page.evaluate("""() => { const e = document.querySelector('.hsw') || document.querySelector('.sw'); if (!e) return null;
                   const b = e.getBoundingClientRect(); const x = b.x + b.width / 2, y = b.y + Math.min(b.height / 2, 20);
                   const top = document.elementFromPoint(x, y); const bar = document.querySelector('.r-bars').getBoundingClientRect();
                   return {switchTop: b.top, switchBottom: b.bottom, barBottom: bar.bottom, covered: !!top && !e.contains(top) && !!top.closest('.r-bars'),
                           langCovered: (() => { const l = document.querySelector('.erp-lang-switch a'); if (!l) return false; const lb = l.getBoundingClientRect(); const t2 = document.elementFromPoint(lb.x + lb.width/2, lb.y + lb.height/2); return !!t2 && !!t2.closest('.r-bars'); })()}; }""")
                report.setdefault('gps_bar', {})[tag] = cov
                if shots:
                    page.screenshot(path=os.path.join(shots, tag + '-gps-bar.png'))
                page.evaluate("riderUx.gps('ok')")

                # Urdu: labels kat rahe hain?
                if lang == 'ur':
                    clip = page.evaluate("""() => Array.from(document.querySelectorAll('.rnav .lb, .rnav .ic')).map(e => ({t: e.textContent.trim(), sh: e.scrollHeight, ch: e.clientHeight, sw: e.scrollWidth, cw: e.clientWidth}))
                        .filter(x => x.sh > x.ch + 1 || x.sw > x.cw + 1)""")
                    report.setdefault('urdu_nav_clipped', {})[tag] = clip
                    navh = page.evaluate("document.querySelector('.rnav').getBoundingClientRect().height")
                    report.setdefault('nav_height', {})[tag] = navh
                else:
                    report.setdefault('nav_height', {})[tag] = page.evaluate("document.querySelector('.rnav').getBoundingClientRect().height")
                ctx.close()

            # 5. naye order ka popup (sirf English, har screen)
            ctx = br.new_context(viewport={'width': w, 'height': h}, device_scale_factor=2 if shots else 1, is_mobile=True, has_touch=True,
                                 permissions=['geolocation'], geolocation={'latitude': 24.86, 'longitude': 67.0})
            page = ctx.new_page()
            serve(page, html_en, top, bottom, poll_offer)
            page.goto('http://t.local/shop/rider/')
            page.wait_for_selector('#offerAlert', timeout=4000)
            page.wait_for_timeout(300)
            oa = page.evaluate("""() => { const y = document.getElementById('oaYes').getBoundingClientRect(); const n = document.getElementById('oaNo').getBoundingClientRect();
                const l = document.getElementById('oaLater').getBoundingClientRect(); const o = document.getElementById('offerAlert');
                return {vh: innerHeight, yesTop: y.top, yesBottom: y.bottom, noBottom: n.bottom, laterBottom: l.bottom, scrolls: o.scrollHeight > o.clientHeight,
                        yesH: y.height, yesVisible: y.bottom <= innerHeight}; }""")
            report.setdefault('offer_popup', {})[name] = oa
            if shots:
                page.screenshot(path=os.path.join(shots, '%s-offer-popup.png' % name))
            ctx.close()
            report.setdefault('guards', {})[name] = guards(br, w, h, top, bottom, html_en, serve, poll_idle, poll_offer)
        br.close()
    return report


def guards(br, w, h, top, bottom, doc, serve, poll_idle, poll_offer):
    """Step 9 ke badlav: reload guard, back button, offline popup."""
    out = {}
    geo = dict(permissions=['geolocation'], geolocation={'latitude': 24.86, 'longitude': 67.0}, is_mobile=True, has_touch=True)
    # a) likha hua reload se nahi mitta (naye offers ka count badalta hai, offer_list khali: reload ka waqt)
    state = {'n': 0}

    def changing():
        state['n'] += 1
        d = dict(poll_idle)
        d['offers'] = 0 if state['n'] < 2 else 1
        return d
    ctx = br.new_context(viewport={'width': w, 'height': h}, **geo)
    page = ctx.new_page()
    serve(page, doc, top, bottom, changing)
    page.goto('http://t.local/shop/rider/')
    page.wait_for_timeout(500)
    page.evaluate("window.__marker = 1")
    page.evaluate("document.querySelector('details.moreact').open = true")
    page.fill('input[name=delivery_otp]', '12') if page.query_selector('input[name=delivery_otp]') else None
    page.evaluate("document.querySelector('input[name=delivery_otp]') && (document.querySelector('input[name=delivery_otp]').closest('details.skip') || document.body).setAttribute('open','')")
    page.evaluate("window.riderUx.pollFailed(); window.riderUx.pollOk();")
    page.evaluate("fetch('/u/rider_poll/')")
    # base.html ka poll 12s mein ek baar chalta hai: seedhe reloadWhenIdle ko bulao (wahi function poll bhi bulata hai)
    page.evaluate("riderUx.reloadWhenIdle(100)")
    page.wait_for_timeout(1500)
    out['reload_blocked_while_typing'] = page.evaluate("window.__marker === 1")
    page.evaluate("document.querySelectorAll('details[open]').forEach(d => d.open = false); document.querySelectorAll('input[type=text]').forEach(i => i.value=''); document.activeElement && document.activeElement.blur && document.activeElement.blur();")
    page.wait_for_timeout(5800)
    out['reload_happens_when_idle'] = (page.evaluate("window.__marker === undefined") if True else None)
    ctx.close()
    # b) back button
    ctx = br.new_context(viewport={'width': w, 'height': h}, **geo)
    page = ctx.new_page()
    serve(page, doc, top, bottom, poll_idle)
    page.goto('http://t.local/shop/rider/')
    page.wait_for_timeout(400)
    n0 = page.evaluate("history.length")
    page.click('#rMoreBtn')
    page.wait_for_timeout(300)
    opened = page.evaluate("document.getElementById('rMore').classList.contains('open')")
    page.go_back()
    page.wait_for_timeout(400)
    out['more_back_closes_sheet'] = bool(opened) and not page.evaluate("document.getElementById('rMore').classList.contains('open')") and page.url.endswith('/shop/rider/')
    page.click('#rMoreBtn'); page.wait_for_timeout(300)
    page.mouse.click(10, 60); page.wait_for_timeout(400)      # sheet ke bahar (andhera hissa) dabana
    out['more_ui_close_keeps_history_clean'] = page.evaluate("history.length") <= n0 + 1 and page.url.endswith('/shop/rider/')
    page.evaluate("riderSos(true)")
    page.wait_for_timeout(200)
    sos_open = page.evaluate("document.getElementById('sosSheet').classList.contains('open')")
    page.go_back()
    page.wait_for_timeout(400)
    out['sos_back_closes_sheet'] = bool(sos_open) and not page.evaluate("document.getElementById('sosSheet').classList.contains('open')") and page.url.endswith('/shop/rider/')
    ctx.close()
    # c) popup: internet band + ACCEPT
    ctx = br.new_context(viewport={'width': w, 'height': h}, **geo)
    page = ctx.new_page()
    serve(page, doc, top, bottom, poll_offer)
    page.goto('http://t.local/shop/rider/')
    page.wait_for_selector('#offerAlert', timeout=4000)
    ctx.set_offline(True)
    page.evaluate("window.dispatchEvent(new Event('offline'))")
    page.click('#oaYes')
    page.wait_for_timeout(400)
    out['popup_offline_no_navigation'] = page.url.endswith('/shop/rider/') and page.evaluate("!document.getElementById('oaYes').disabled")
    ctx.close()
    # d) popup: Android back = "Later" (popup band, page se bahar nahi); "Later" dabane se history saaf rahe
    ctx = br.new_context(viewport={'width': w, 'height': h}, **geo)
    page = ctx.new_page()
    serve(page, doc, top, bottom, poll_offer)
    page.goto('http://t.local/shop/rider/')
    page.wait_for_selector('#offerAlert', timeout=4000)
    n1 = page.evaluate("history.length")
    page.go_back()
    page.wait_for_timeout(400)
    out['popup_back_closes'] = page.evaluate("!document.getElementById('offerAlert')") and page.url.endswith('/shop/rider/')
    ctx.close()
    ctx = br.new_context(viewport={'width': w, 'height': h}, **geo)
    page = ctx.new_page()
    serve(page, doc, top, bottom, poll_offer)
    page.goto('http://t.local/shop/rider/')
    page.wait_for_selector('#offerAlert', timeout=4000)
    n2 = page.evaluate("history.length")
    page.click('#oaLater')
    page.wait_for_timeout(500)
    out['popup_later_keeps_history_clean'] = page.evaluate("!document.getElementById('offerAlert')") and page.url.endswith('/shop/rider/') and not page.evaluate("history.state && history.state.rtrap")
    ctx.close()
    return out


def summarize(rep):
    lines = []
    lines.append('== 1. 44px se chhote buttons / links ==')
    for tag, items in rep['small_targets'].items():
        lines.append('%s: %d' % (tag, len(items)))
        for i in items[:12]:
            lines.append('    %-18s %-32s %dx%d' % (i['tag'], i['label'], i['w'], i['h']))
    lines.append('\n== 2. Takrao ==')
    lines += ['  ' + x for x in rep['overlaps']] or ['  koi nahi']
    for tag, c in rep.get('chip', {}).items():
        if c['chipOverlapsSos'] or c['chipOverlapsNav']:
            lines.append('  %s: location ki patti: SOS se takra=%s, bar se takra=%s' % (tag, c['chipOverlapsSos'], c['chipOverlapsNav']))
    for tag, c in rep.get('sos_covers', {}).items():
        lines.append('  %s: SOS button in ke upar aa jata hai (scroll ke aakhir par): %s' % (tag, c))
    lines.append('\n== 3. More sheet ==')
    for tag, m in rep['more'].items():
        lines.append('  %s: %s' % (tag, m))
    lines.append('\n== 4. GPS patti vs Online switch ==')
    for tag, m in rep['gps_bar'].items():
        lines.append('  %s: %s' % (tag, m))
    lines.append('\n== 5. Naye order ka popup ==')
    for tag, m in rep['offer_popup'].items():
        lines.append('  %s: %s' % (tag, m))
    lines.append('\n== 6. Urdu: neeche ki bar ke labels kat rahe hain ==')
    for tag, m in rep.get('urdu_nav_clipped', {}).items():
        lines.append('  %s: %s' % (tag, m or 'theek'))
    lines.append('\n== 7. Step 9 guards (True = theek) ==')
    for tag, m in rep.get('guards', {}).items():
        lines.append('  %s: %s' % (tag, m))
    lines.append('\nNeeche ki bar ki unchai (px): %s' % rep['nav_height'])
    return '\n'.join(lines)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--shots')
    ap.add_argument('--json')
    a = ap.parse_args()
    rep = run(a)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=1)
    print(summarize(rep))
