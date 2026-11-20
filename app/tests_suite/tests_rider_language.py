"""Step 6: rider pages English mein hain aur Urdu rider_step6.py / dictionary se aati hai.
Jo templates "done" list mein hain unka har English text tarjuma hona zaroori hai (scripts/rider_i18n_audit.py)."""
import importlib.util
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
RIDER_DIR = ROOT / 'templates' / 'customer_portal' / 'rider'

# Jo parts mukammal ho chuke (har part ke baad yahan templates jodte jayen)
DONE = [
    'home.html', '_order_card.html', '_rider_menu.html', '_act_pickup.html', '_act_deliver.html', 'base.html',
    'history.html', 'earnings.html', '_payout.html', '_goals.html',
    'shifts.html', 'hotspots.html', 'documents.html', 'settings.html', '_battery_saver.html', '_live_location.html',
    'disputes.html', 'dispute_detail.html', 'review.html', 'support.html', '_support_chat.html',
    'login.html', 'register.html', 'forgot_password.html', 'reset_password.html',
    # Part 6: baqi rider-facing aur chhote admin-side templates (jin mein ab koi English tarjuma se nahi rehta)
    'detail.html', 'support_thread.html', 'support_admin.html', 'returns_admin.html', 'sos_admin.html',
    'navigate.html', 'batch_navigate.html',
]


def _audit():
    spec = importlib.util.spec_from_file_location('rider_i18n_audit', ROOT / 'scripts' / 'rider_i18n_audit.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RiderCatalog(SimpleTestCase):
    def test_placeholders_match(self):
        from app.i18n import rider_step6 as r
        for name in ('RIDER_TAG', 'RIDER_CATALOG'):
            for en, ur in getattr(r, name):
                self.assertEqual(en.count('{}'), ur.count('{}'), '{} count alag hai: %s' % en)

    def test_no_single_quote_in_urdu(self):
        from app.i18n import rider_step6 as r
        for name in ('RIDER_DEFAULTS', 'RIDER_TAG', 'RIDER_CATALOG'):
            for en, ur in getattr(r, name):
                import re
                self.assertNotIn("'", re.sub(r'<[^>]*>', '', ur), 'Urdu text mein single quote nahi: %s' % en)

    def test_no_duplicate_keys(self):
        from app.i18n import rider_step6 as r
        for name in ('RIDER_DEFAULTS', 'RIDER_TAG'):
            keys = [en.lower() for en, _ in getattr(r, name)]
            self.assertEqual(len(keys), len(set(keys)), name + ' mein dohra key')


class RiderTemplatesTranslated(SimpleTestCase):
    def test_done_templates_fully_translated(self):
        a = _audit()
        keys = a.known_keys()
        bad = []
        for name in DONE:
            src = (RIDER_DIR / name).read_text(encoding='utf-8')
            bad += ['%s: {%% t %%} %s' % (name, t) for t in a.tag_texts(src) if a.core(t) not in keys]
            for n in a.text_nodes(src):
                c = a.core(n)
                import re
                if re.search(r'[A-Za-z]{2}', c) and not re.fullmatch(r'[x0-9 +\-]+', c) and c not in keys:
                    bad.append('%s: %s' % (name, n))
        self.assertEqual(bad, [], 'Urdu tarjuma nahi mila:\n' + '\n'.join(bad))

    def test_tag_renders_urdu_with_values(self):
        from django.template import Context, Template
        out = Template('{% load portal_i18n %}{% t "Batch route — {} orders together" n %}').render(
            Context({'LANG_CODE': 'ur', 'n': 3}))
        self.assertIn('3', out)
        self.assertIn('بیچ روٹ', out)
        en = Template('{% load portal_i18n %}{% t "Batch route — {} orders together" n %}').render(
            Context({'LANG_CODE': 'en', 'n': 3}))
        self.assertEqual(en, 'Batch route — 3 orders together')


class RiderViewMessages(SimpleTestCase):
    def test_rider_view_messages_have_urdu(self):
        """views_rider_portal / nav / payouts / sos ke seedhe messages (admin wale nahi) catalog mein hon."""
        from app.i18n.server_t import translate
        for text in (
            'ℹ️ You have no active orders to navigate.',
            '✅ Request for Rs. 500 sent. You will be notified when it is paid.',
            '↩️ Order #12 given back. It goes to other riders now.',
            'SOS is currently unavailable. Call 999 if you are in danger.',
            '🔒 Too many attempts. Please try again later.',
            '🎉 Order #12 delivered. Earnings: Rs. 50.',
            '🏆 Daily goal completed! Bonus: Rs. 30.',
            '❌ Your application was rejected. Please upload your documents again or contact the admin.',
            '⛔ Your account is suspended: late Please contact the admin.',
            'The minimum request is Rs. 500.',
            'Your application was rejected: bad photo Please upload your documents again or contact the admin.',
        ):
            self.assertNotEqual(translate(text, 'ur'), text, 'Urdu nahi mila: ' + text)


class RiderPasswordPolicyUrdu(SimpleTestCase):
    """Part F2-1: password policy errors (rider register / settings / reset) Urdu mein aate hain."""

    def test_policy_messages_translate(self):
        from app.i18n.server_t import translate
        from app.utils.password_policy import password_errors
        for pw, hints in (('abc', ()), ('12345678', ()), ('aaaaaaaa1', ()), ('password1', ()), ('Ali12345xyz', ('Ali12345',))):
            for msg in password_errors(pw, hints):
                self.assertNotEqual(translate(msg, 'ur'), msg, 'Urdu nahi mili: %s' % msg)


class RiderStep7Files(SimpleTestCase):
    """Step 7: internet / GPS patti, loading nishan (static/js/rider_ux.js) har rider page par load ho."""

    def test_rider_ux_loaded_by_base(self):
        base = (RIDER_DIR / 'base.html').read_text(encoding='utf-8')
        self.assertIn('js/rider_ux.js', base)
        self.assertIn('riderUx.pollFailed', base)

    def test_rider_ux_api_and_urdu_text(self):
        import re
        js = (ROOT / 'static' / 'js' / 'rider_ux.js').read_text(encoding='utf-8')
        for name in ('window.riderUx', 'pollOk', 'pollFailed', 'gps:', 'busy:'):
            self.assertIn(name, js)
        # Urdu jumle ' ke baghair (JS ki single quote wali string toot jati hai): har "ur ? '...'" ke baad ":" aaye
        found = re.findall(r"ur \? '([^']*)'\s*(.)", js)
        self.assertGreaterEqual(len(found), 5)
        for text, nxt in found:
            self.assertEqual(nxt, ':', 'Urdu jumle mein quote: ' + text)


class RiderStep9Files(SimpleTestCase):
    """Step 9: Step 8 ki bugs ke fix wapas na bigar jayen (file ke andar ke nishan)."""

    def _read(self, *parts):
        return (ROOT.joinpath(*parts)).read_text(encoding='utf-8')

    def test_bars_do_not_cover_header(self):
        css = self._read('static', 'css', 'rider.css')
        self.assertIn('.r-bars{position:sticky', css)          # W1: patti content dhakti nahi
        self.assertIn('.top .erp-lang-switch a', css)           # W2: language links 44px
        self.assertIn('body.has-sos', css)                      # W4: SOS ke liye neeche jagah
        self.assertIn('env(safe-area-inset-top', css)           # W7

    def test_reload_waits_for_idle(self):
        base = self._read('templates', 'customer_portal', 'rider', 'base.html')
        js = self._read('static', 'js', 'rider_ux.js')
        self.assertIn('riderUx.reloadWhenIdle', base)           # W3
        self.assertIn('reloadWhenIdle', js)
        self.assertIn('busyTyping', js)

    def test_back_button_and_popup_guard(self):
        base = self._read('templates', 'customer_portal', 'rider', 'base.html')
        menu = self._read('templates', 'customer_portal', 'rider', '_rider_menu.html')
        self.assertIn("riderUx.trap('sos'", base)               # W11
        self.assertIn("riderUx.trap('more'", menu)
        self.assertIn('riderUx.isOnline()', base)               # W6
        self.assertIn("class=\"has-sos\"", base)

    def test_js_texts_are_translatable(self):
        from app.i18n import rider_step6 as r
        keys = {en.lower() for en, _ in r.RIDER_DEFAULTS} | {en.lower() for en, _ in r.RIDER_TAG}
        for k in ('new order', 'later (stays in the list)', 'from store', 'cod', 'no internet', 'saving location',
                  'order handed to the customer?', 'location permission is needed. open settings?'):
            self.assertIn(k, keys, 'Urdu nahi: ' + k)               # W8
        popup = self._read('templates', 'customer_portal', 'rider', 'base.html')
        self.assertIn('<span>NEW ORDER</span>', popup)

    def test_live_location_fallbacks(self):
        loc = self._read('templates', 'customer_portal', 'rider', '_live_location.html')
        self.assertIn('fallbackWeb', loc)                        # W12a: plugin fail to web GPS
        self.assertIn("'auth'", loc)                             # W12d: session khatam
        self.assertNotIn('using less GPS power', self._read('templates', 'customer_portal', 'rider', '_battery_saver.html'))

    # ---- Step 9 baqi kaam: popup back, notification jawab Urdu, APK back plugin ----
    def test_popup_back_button(self):
        base = self._read('templates', 'customer_portal', 'rider', 'base.html')
        self.assertIn("riderUx.trap('offer'", base)              # popup par back = "Later"
        self.assertIn('function dismissAlert', base)
        self.assertIn('t.leave(function(){ post(url); })', base)  # ACCEPT / Reject par extra history entry nahi bachti

    def test_apk_back_plugin(self):
        js = self._read('static', 'js', 'rider_ux.js')
        wf = (ROOT / '.github' / 'workflows' / 'deploy.yml').read_text(encoding='utf-8')
        self.assertIn("addListener('backButton'", js)           # A4
        self.assertIn('@capacitor/app@^7', wf)

    def test_notification_reply_language(self):
        java = self._read('android_assets', 'rider_actions', 'RiderActionReceiver.java.txt')
        self.assertIn('erp_lang=', java)                        # A3: cookie se language
        self.assertIn('\\"lang\\"', java)
        from app.i18n.server_t import translate
        for en in ('Order declined.', 'Please go Online in the app first.', 'Your rider account is not active.',
                   'This button has expired. Please open the app.', 'Something went wrong. Please open the app.'):
            self.assertNotEqual(translate(en, 'ur'), en, 'Urdu nahi: ' + en)
        for en in ('Order #5 is yours. Pick it up from Shop.', 'You already have 3 orders.'):
            self.assertNotEqual(translate(en, 'ur'), en, 'Urdu nahi: ' + en)
