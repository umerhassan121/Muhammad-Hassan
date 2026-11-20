# Customer Step 2 - shared menu (neeche 5 tab bar + Account sheet)

## Naya
- app/customer/shop_menu.py      : faisle (tab, flags, badge, active, kahan chhupe) + context processor `menu_flags`
- app/templatetags/shop_menu_tags.py : `{% shop_menu %}`
- templates/customer_portal/_shop_menu.html : bar + Account sheet (CSS/JS abhi yahin; Step 4 mein shop.css)
- app/tests_suite/tests_shop_menu.py : 12 tests

## Badla
- P1/settings.py : context processor `app.customer.shop_menu.menu_flags` (SHOP_MENU_ON, SHOP_BAR_ON)
- base_shop.html : `{% shop_menu %}` navbar ke baad; customer pages par hamburger + sidebar + overlay nahi
  (`{% if not SHOP_MENU_ON %}`); body class has-shop-menu / has-shop-bar; viewport-fit=cover (sirf customer pages);
  purani .app-bottom-nav / .mobile-bottom-nav CSS hata di; cart badge sync ab `[data-sm-cart]` par;
  mobile par header ka Cart aur user chip chhupe (bar mein hain)
- 6 pages ki bar ki nakal hata di: shop, stores, my_orders, order_detail, order_tracking, account/dashboard
- Purani `.mobile-bottom-nav` / `.app-bottom-nav` CSS baqi customer pages se bhi hata di (cart, checkout, place_order,
  track_order, order_success, auth/*)
- product_detail.html : Add to cart patti bar ke ooper (padding)

## Qaidey
- Vendor / Rider pages (url vendor_* / rider_*, path /shop/vendor/, /shop/rider/) par purana hamburger sidebar hi hai; unhe haath nahi lagaya.
- Cart, Checkout, Place order par bar mobile par chhupi (desktop par patti rehti hai).
- Desktop (>=992px): bar header ke neeche seedhi patti; Account sheet kone mein popup.
- Account tab: JS na chale to seedha my_account (login ke baghair customer_login) khulta hai.
- URL names, order logic, JS (cart add, tracking) nahi chhede.

## Jo abhi nahi hua (agle steps)
- store_detail ki cart patti (.cb) ka offset diya hai, par uska padding Step 6 mein dekhenge.
- Account sheet ke jumle abhi English (Step 7 mein {% t %} + Urdu).
- CSS shop.css mein Step 4 mein.
- Android back button se sheet band hona, notch/safe-area: Step 9 phone test.
