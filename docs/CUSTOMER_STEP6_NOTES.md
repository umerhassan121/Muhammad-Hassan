# Customer Step 6 - Menu aur style baqi pages par

## Naya (static/css/)
Har page ka apna CSS, sirf us page par `{% block extra_css %}` se load hota hai (koi global leak nahi):
shop_store_detail, shop_product_detail, shop_my_orders, shop_order_detail, shop_order_tracking, shop_wallet,
shop_favorites, shop_repeat_plans, shop_pro, shop_account, shop_login, shop_register, shop_forgot_password
(forgot + reset dono), shop_verify_login_otp, shop_verify_otp_later, shop_pending_otps, shop_info (help / faq / about /
returns / terms / privacy ka base_info). Sab `.css` ?v=1 ke saath.

## Badla
- 18 templates se saare <style> block nikal diye (sab mein template tag se pare the, to kuch nahi tootta)
- Menu: Step 2 se sab customer pages par shared bar hai. Ab mapping mein ye bhi: forgot_password, reset_password,
  verify_otp_later -> Account tab; track_live_public -> Orders tab (app/customer/shop_menu.py)
- Tap size 44px+ (har page CSS ke aakhir mein "Step 6: tap size" hissa):
  * product detail: qty + / - 44x44 (pehle 36 / 32), Add 48px
  * store detail: back 44x44, qty step 44x44 (pehle 42x38 / 36), tabs 44px, Add 44px, cart patti button 48px
  * favourites: tabs aur chips 44px; wallet / pro buttons 48px; account: referral / Shop now 44px
  * tracking: rider call aur action buttons 44px; help pages ki pills 44px; login / register password dikhane ka button 44x44
  * my_orders / order_detail / wallet / account / repeat_plans: phone par `.btn-sm` 44px
- Inline style="" -> class (store_detail 30, wallet 11, order_detail 5, product_detail 5, pro 3, my_orders 5 alag styles).
  Naam `sdx1`, `wlx1`, `odx1`, `pdx1`, `prx1`, `mox1` (page CSS ke aakhir mein). Dohri class (`.sdx1.sdx1`) taake zor wahi rahe jo
  inline ka tha.
  Nahi badle: jin mein `display`, `!important`, ya `{{ }}` / `{% %}` hai (JS se show / hide hota hai, ya value server se aati hai),
  aur <script> ke andar ke strings.
- Conditional (`{% if %}`) ke andar ke <style> ab hamesha load hote hain (sirf class rules, behtar ke liye kuch nahi badalta).

## Jo nahi chheda
- URL names, views, JS, order / payment / tracking logic, Vendor / Rider pages
- chat_widget.html, _order_chat_panel.html ke apne <style> (Step 9 mein chat button ka bar se takrao dekhenge)
- Mix-language jumle: Step 7

## Dekhna hai (phone par, 320 / 360 / 390 px, English aur Urdu, login ke saath aur baghair)
- Store detail (tabs, qty step, cart patti), product detail (qty, Add patti bar ke ooper), My orders, order detail,
  tracking (map, rider call), wallet, favourites, repeat orders, pro, account, login / register / forgot password, help pages
- Har page par neeche ki bar aur sahi tab active
- Koi button / card pehle se alag shakal ka to screenshot bhejein (khaas kar inline se class wale hisse)
- Hard refresh karein. Tests: python manage.py test app.tests_suite.tests_shop_css app.tests_suite.tests_shop_menu
