# Naya theme (Market Editorial) — saare shop pages par

## Naya / badla
- static/css/shop_theme_pages.css (naya): cream + ink + tangerine theme baqi saare customer pages par — cart, checkout/place order,
  order success, stores, store detail, product detail, login/register/forgot/OTP pages, account, my orders, order detail/tracking,
  wallet, favorites, repeat plans, pro, info pages, public tracking.
- templates/customer_portal/base_shop.html: shop_theme.css ke baad is file ka link (sirf jab path /shop/vendor/ na ho).
- Sirf rang / border / shadow / font. HTML, JS, classes, views, cart/order logic ko haath nahi lagaya.

## Vendor pages
- /shop/vendor/ par yeh file load nahi hoti (wahan .stat-card, .page-header jaisi common classes hain); un par sirf global shop_theme.css lagti hai.

## Dekhna hai
- Hard refresh (Ctrl+F5); deploy par `collectstatic`.
- Cart, checkout, product, store detail, login/register, account, orders, wallet — phone par ek ek dekh lein.
- Rang badalne hon to shop_theme.css ke --t-* tokens.

## v2.1 — Home: "Stores near you" aur "Trending near you" ka naya design
- shop_theme.css (v=3): store card (lamba cover, ink border + hard shadow, gol logo, time/fee/rating chips, neeche dashed "Min order" patti, "See all" peela card).
- Trending / Favourites card: square photo poori dikhti hai (contain), 2-line naam, store ka naam chip, bold price.
- Sirf CSS; markup/logic wahi. Stores page ka card bhi yahi (_store_tile.html shared hai).

## v2.2 — Home: "Hot deals" aur "All products" ka naya design
- shop_theme.css (v=4): deal card (square photo, % OFF sticker, 2-line naam, bold price), product card (ink border, square photo, 2-line naam, price bold, ink "Add" + sun "Buy" button, in-cart par hara border).
- shop.html: price ab `floatformat:"-2"` (76.00 ki jagah 76; 76.50 ho to 76.50) aur "Rs." -> "Rs".
