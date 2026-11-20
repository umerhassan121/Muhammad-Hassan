# Customer Step 4 - Ek hi style: static/css/shop.css

## Naya
- static/css/shop.css (~103 KB) : customer portal ka ek style. Hissay:
  0. Tokens (--shop-*: rang, radius, gap, tap size) - naye kaam yahan se rang / size lein
  1. Base (base_shop.html ka purana ~2,760 line inline CSS, bilkul wahi, sirf jagah badli)
  2. Voice / mic button
  3. Shop menu (.sm-*, _shop_menu.html se)
  4. Store tile (.stl, _store_tile_css.html se)
- app/tests_suite/tests_shop_css.py : 4 tests

## Badla
- base_shop.html : 161 KB -> 70 KB. Bara <style> hata kar `<link href="{% static 'css/shop.css' %}?v=1">`. Voice wala <style> bhi gaya.
  Sirf do chhote flag wale <style> rahe (search / voice off hone par chhupane ke liye; unmein template tag hai).
- _shop_menu.html : CSS nikal di (HTML / JS wahi).
- _store_tile_css.html : ab khali (sirf comment); shop.html / stores.html ke include na toote.

## Shakal nahi badli
- CSS ka order wahi: base -> voice -> menu -> tile. Selectors / rules waise ke waise (brace count check kiya).
- Naya sirf tokens ka :root (--shop-*), jo abhi kahin use nahi hota.
- Views, URLs, JS, cart / order logic ko haath nahi lagaya.

## Dekhna hai (phone par, pehle jaisa hi lagna chahiye)
- Home, Stores, Cart, Orders, Account sheet, login / register, store detail (sab pehle jaise).
- Neeche ki bar aur Account sheet, store card, voice mic button.
- Browser mein hard refresh (Ctrl+F5) / purana cache saaf; naya CSS /static/css/shop.css?v=1 se aata hai.
- Deploy par `collectstatic` chalana (agar aap chalate hain) taake shop.css staticfiles mein aa jaye.

## Jo abhi nahi hua (agle steps)
- Page ke apne <style> (shop ~1,190, checkout ~720, product_detail ~380 line) aur inline style="" Step 5-6 mein pages ke saath shop.css mein jayenge.
- Purani dead CSS (.store-card / .st-card) ki safai Step 6 mein, jab saare pages dekh liye jayen.
- Test chalane ke liye yahan Django nahi tha: tests ko `python manage.py test app.tests_suite.tests_shop_css app.tests_suite.tests_shop_menu` se chalayein.
