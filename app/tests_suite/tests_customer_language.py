"""Customer Step 7: customer pages English mein hain aur Urdu app/i18n/customer_step7.py se aati hai.
Jo templates DONE list mein hain unka har English text tarjuma hona zaroori hai (scripts/customer_i18n_audit.py).
Har part ke baad DONE mein templates jodte jayen."""
import importlib.util
import re
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
CUSTOMER_DIR = ROOT / 'templates' / 'customer_portal'

DONE = [
    # Part 1: shared menu, store card / tile
    '_shop_menu.html', '_store_card.html', '_store_tile.html',
    # Part 2: Home, Stores, Store detail, Product, offers
    'shop.html', 'stores.html', 'store_detail.html', 'product_detail.html',
    '_offer_box.html', '_offer_rows.html', '_option_group.html',
    # Part 3: Cart, Checkout, Order success
    'cart.html', 'checkout.html', 'place_order.html', 'order_success.html', 'order_success_auto.html',
    # Part 4: Orders, Order detail, Tracking, Chat
    'my_orders.html', 'order_detail.html', 'order_tracking.html', 'track_order.html', 'track_order_public.html',
    '_drop_pin.html', '_live_map.html', '_order_chat_panel.html', 'chat_widget.html', '_order_polish.html',
    '_push_prompt.html', '_fav_js.html',
    # Part 5: Wallet, Favourites, Repeat orders, Pro, Account, Delete account
    'wallet.html', 'favorites.html', 'repeat_plans.html', 'pro.html',
    'account/dashboard.html', 'account/delete_account.html',
    # Part 6: Login, Register, Password, OTP pages
    'auth/login.html', 'auth/register.html', 'auth/forgot_password.html', 'auth/reset_password.html',
    'auth/verify_login_otp.html', 'auth/verify_otp_later.html', 'auth/pending_otps.html',
    # Part 7: Help and info pages
    'info/base_info.html', 'info/about.html', 'info/faq.html', 'info/help.html',
    'info/returns.html', 'info/terms.html', 'info/privacy.html',
]


def _audit():
    spec = importlib.util.spec_from_file_location('customer_i18n_audit', ROOT / 'scripts' / 'customer_i18n_audit.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CustomerCatalog(SimpleTestCase):
    def test_placeholders_match(self):
        from app.i18n import customer_step7 as c
        for name in ('CUSTOMER_TAG', 'CUSTOMER_CATALOG'):
            for en, ur in getattr(c, name):
                self.assertEqual(en.count('{}'), ur.count('{}'), '{} count alag hai: %s' % en)

    def test_no_single_quote_in_urdu(self):
        from app.i18n import customer_step7 as c
        for name in ('CUSTOMER_DEFAULTS', 'CUSTOMER_TAG', 'CUSTOMER_CATALOG'):
            for en, ur in getattr(c, name):
                self.assertNotIn("'", re.sub(r'<[^>]*>', '', ur), 'Urdu text mein single quote nahi: %s' % en)

    def test_no_duplicate_keys(self):
        from app.i18n import customer_step7 as c
        for name in ('CUSTOMER_DEFAULTS', 'CUSTOMER_TAG'):
            keys = [en.lower() for en, _ in getattr(c, name)]
            self.assertEqual(len(keys), len(set(keys)), name + ' mein dohra key')

    def test_catalog_is_registered(self):
        from app.i18n import customer_step7 as c, i18n_default, portal_messages
        defaults = {en for en, _ in i18n_default.DEFAULTS}
        tags = {en for en, _ in portal_messages.TAG_ONLY}
        self.assertTrue(all(en in defaults for en, _ in c.CUSTOMER_DEFAULTS))
        self.assertTrue(all(en in tags for en, _ in c.CUSTOMER_TAG))


class CustomerTemplatesTranslated(SimpleTestCase):
    def test_done_templates_fully_translated(self):
        a = _audit()
        keys = a.base.known_keys()
        bad = []
        for name in DONE:
            src = (CUSTOMER_DIR / name).read_text(encoding='utf-8')
            for t in a.untranslated(src, keys):
                if t == 'EN' or '\x00' in t:   # EN = language button; \x00 = {% if %} wale placeholder ke tukre (tukre alag alag tarjuma hain)
                    continue
                bad.append('%s: %s' % (name, t))
            for t in a.roman_urdu(src):
                bad.append('%s: [Roman Urdu] %s' % (name, t))
            if a.lang_ifs(src):
                bad.append('%s: purani LANG_CODE nakal baqi' % name)
        self.assertEqual(bad, [], 'Step 7 baqi:\n' + '\n'.join(bad))

    def test_base_shop_texts_use_tag(self):
        src = (CUSTOMER_DIR / 'base_shop.html').read_text(encoding='utf-8')
        self.assertIn('{% load portal_i18n %}', src)
        self.assertNotIn("{% if LANG_CODE == 'ur' %}مائیکروفون", src)

    def test_tag_renders_urdu_with_values(self):
        from django.template import Context, Template
        tpl = '{% load portal_i18n %}{% t "{} in your cart." n %}'
        ur = Template(tpl).render(Context({'LANG_CODE': 'ur', 'n': 3}))
        self.assertIn('3', ur)
        self.assertIn('کارٹ', ur)
        self.assertEqual(Template(tpl).render(Context({'LANG_CODE': 'en', 'n': 3})), '3 in your cart.')
