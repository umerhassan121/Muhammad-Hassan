# Customer Portal - Step 1: Final navigation map (code se verified)

Is step mein koi template / CSS / Python code nahi badla. Sirf ye final naqsha (Step 2 isi par banega).

## Neeche ki bar (5 tab, Cart darmiyan mein)
| # | Tab | URL name | Icon (bootstrap-icons) | Kab dikhe | Badge |
|---|-----|----------|------------------------|-----------|-------|
| 1 | Home | shop_home | bi-house-door | hamesha | - |
| 2 | Stores | store_list | bi-shop | SHOP.shop_stores_enabled | - |
| 3 | Cart | cart_view | bi-cart3 | hamesha | cart_count |
| 4 | Orders | my_orders | bi-receipt | login ke baad | jari orders ki ginti |
| 4b | Track | track_order | bi-geo-alt | login ke baghair, SHOP.order_tracking_enabled | - |
| 5 | Account | my_account | bi-person | hamesha | baad mein |

Stores off => bar 4 tab. Cart / Checkout / Place order par bar chhupi, uski jagah ek bara button.

## Account sheet (har item apne flag par)
Wallet (shop_wallet_enabled, wallet_page), Pro (shop_pro_enabled, pro_page),
Favourites (shop_favorites_enabled, favorites_page), Repeat orders (repeat_plans),
Language (English / Urdu), Help (shop_help) + About/Returns/Terms/Privacy, Rabta,
Logout. Login ke baghair: Login (customer_login_enabled) / Register (customer_register_enabled).
Neeche "Hamare saath kaam karein": vendor_login/register, rider_login/register (apne flags par).

## 6 sawalon ke jawab (aap ne plan ke sujhao manzoor rakhe)
1 Haan 5 tab | 2 Haan Track | 3 Haan bara action button | 4 Haan Account mein | 5 Sirf English + Urdu | 6 Haan APK Step 9 mein

## Code mein jo mila (Step 2 ke liye)
- Bar ka copy: shop, stores, my_orders, order_detail, order_tracking, account/dashboard (6 jagah); sab mein Home/Stores/Orders/Cart (4 tab).
- base_shop.html:55 purani .mobile-bottom-nav (display:none), :2737 .app-bottom-nav CSS.
- cart.html / checkout.html / place_order.html / account/dashboard.html mein .mobile-bottom-nav hide.
- Flags SHOP.* context_processors.py se aate hain. NOTE: cart_count ka context processor app/config/context_processors.py mein nahi mila; Step 2 mein dekh kar wahi se badge lagayenge. Jari-order ginti ka source bhi Step 2 mein.
- Hamburger sidebar mein vendor/rider links base_shop.html ~3240-3350.
- URL names nahi badlenge.
