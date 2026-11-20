# Customer Step 7 - Language ek karna (ek page = ek language)

Tareeqa (rider / vendor jaisa): customer pages English mein likhe jate hain, Urdu `app/i18n/customer_step7.py` se aati hai.
- CUSTOMER_DEFAULTS: seedhe labels / placeholders (browser dictionary)
- CUSTOMER_TAG: `{% t "... {} ..." value %}` jumle (English aur Urdu mein {} barabar, Urdu mein ' nahi)
- CUSTOMER_CATALOG: views ke messages
Check: `python3 scripts/customer_i18n_audit.py [file.html]` aur `python manage.py test app.tests_suite.tests_customer_language`

## Part 1 - catalog jorna + shared hisse (done)
- customer_step7.py ab i18n_default.py (DEFAULTS) aur portal_messages.py (TAG_ONLY, CATALOG) se jura hai (pehle jura nahi tha)
- _shop_menu, _store_card, _store_tile: baqi English ka Urdu
- base_shop: mic ke 2 error + "Searching for" ab {% t %}; voice ke title / aria-label ka Urdu
- tests_customer_language.py (nayi), DONE list mein 3 templates

## Part 2 - Home, Stores, Store detail, Product, offers (done)
- shop, stores, store_detail, product_detail, _offer_box, _offer_rows, _option_group: Roman Urdu hataya
  (Apna area chunein, Cart mein {} hai, Wallet se ada, Cash dena hai, Lazmi / Marzi ...)
- purani `{% if LANG_CODE == 'ur' %}` nakal 16 jagah se hatai, ab ek English text + catalog
- JS ke messages (product detail: cart note, notify button) ab {% t %} se
- Jo nahi chheda: shop.html ke andar ke JS ke baqi alert / toast (Part 8 mein views ke saath dekhenge)

## Part 3 - Cart, Checkout, Order success (done)
- cart.html (16) aur checkout.html (24): purani `{% if LANG_CODE == 'ur' %}` nakalein hatain; Urdu wahi rahi jo pehle thi, ab catalog mein
- Roman Urdu: "Store band hai", "Aapka Order Token", "Shukriya" -> English + Urdu
- "Resend in 5:00" timer (HTML + JS) ab {% t %} se; page titles (Cart -, Checkout - ...) ka Urdu
- Order / payment / coupon / place_order ka logic nahi chheda (sirf text)

## Baqi parts
4 Orders / Detail / Tracking / Chat
5 Wallet / Favourites / Repeat / Pro / Account | 6 Login / Register / OTP / Password | 7 Help / FAQ / Terms ... | 8 Views ke messages + final audit
