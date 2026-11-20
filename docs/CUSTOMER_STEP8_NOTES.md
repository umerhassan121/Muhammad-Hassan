# Customer Step 8 - Khali aur galti ki screens (Naya customer ruk nahi jata)

## Nayi files
- static/js/shop_ux.js: internet patti, toast, button spinner, dobara dabne se bachao, shopUx.fetchJson (offline / timeout / session / server / html / 404 pehchanta hai). Vendor pages par load nahi hota.
- templates/customer_portal/_empty_state.html: sab khali screens ek jaisi (icon, title, text, 1-2 button).
- static/css/shop.css hissa 5 (version ?v=2): .s-offline, .s-toast, .is-loading, .s-empty, .s-notice.
- app/tests_suite/tests_customer_step8.py, scripts/checks_and_tests/customer_step8_ux_check.py (Chromium 360x640).

## Badlav
- Khali screen: cart, my_orders (filter par "Show all orders"), stores, store_detail, favourites (2), wallet, repeat_plans, shop (server wali).
- Checkout: Place Order / Verify OTP ab shopUx.fetchJson se. Jawab na aaye (internet toota, timeout, 500) to button band rehta hai aur patti batati hai "My Orders dekh lein" + My Orders / Back to cart / Try again. Saaf inkaar ya session khatam par button wapas khulta hai. Server ka 30 second duplicate guard nahi chheda.
- alert() hata diye: cart, checkout, favourites, _fav_js, product_detail, order_detail (cancel), shop (area save), voice search, order chat (rider / vendor par shopUx na ho to purana alert).
- Roman Urdu hataya: product options ("Pehle ... chunein", "ziyada se ziyada"), location save error.
- checkout.html ka ajeeb {% t "Confirm order</h5>" %} theek kiya.
- app/i18n/customer_step7.py: Part 8 ke jumle (Urdu).

## Test
- Chromium check: 20 / 20 pass (3 click = 1 POST, spinner, offline patti, link / form rok, toast bar ke ooper, fetch errors, Urdu).
- customer_i18n_audit.py: Roman Urdu 0. Template tags (if/for/block/with) barabar.
- Django install nahi tha: templates asli render nahi hue, tests_customer_step8.py chala nahi. Server par chalayein:
  python manage.py test app.tests_suite.tests_customer_step8

## Nahi chheda
- place_order.html (koi render nahi karta), order lagane ka logic, tracking map / chat ke background poll (internet patti kaam chala deti hai).
- login.html mein "Password bhool gaye?" Roman Urdu hai (Step 6 / 7 ka hissa).

## Step 10 - bugs theek (final)
- Roman Urdu ke 5 bache hue jumle English + Urdu kiye (login, product note, checkout x2, order detail); customer_i18n_audit.py ki list barhai; tests_customer_step8.py mein test.
- Step 9 ki list: docs/CUSTOMER_STEP9_BUG_LIST.md
