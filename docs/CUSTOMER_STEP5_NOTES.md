# Customer Step 5 - Cart aur Checkout

## Naya
- static/css/shop_cart.css      : cart.html ka CSS (pehle 2 <style> block, ~115 line)
- static/css/shop_checkout.css  : checkout.html ka CSS (pehle ~720 line <style>)
  Dono sirf apne page par `{% block extra_css %}` se load hoti hain, is liye baqi pages par koi asar nahi
  (checkout ke `.card`, `body{background}`, `.spinner` jaise global-numa rules leak nahi karte).
- app/tests_suite/tests_shop_css.py mein 4 naye tests (CartCheckoutCssTests)

## Cart (cart.html)
- Qty + / - button 44x44 (pehle 36 / 32), qty ki patti 44px unchi (pehle 40 / 36); mobile ke chhote override hata diye
- Remove button kam az kam 44px
- "Total + Checkout" patti: safe-area (notch / gesture bar) ka padding, button 48px, body ka neeche ka gap safe-area ke saath
- Neeche ki bar cart par mobile par pehle se chhupi hai (Step 2, .sm-nobar), is liye patti bar se nahi takrati
- Store band / minimum order: patti mein ab Total ke neeche wajah (English / Urdu): "Store is closed right now" /
  "Add Rs. X more to order". Button pehle ki tarah disabled
- Desktop wali "Proceed to Checkout" patti 48px+

## Checkout (checkout.html)
- Place Order se pehle (dono jagah: skip_otp aur OTP-verified) store band / minimum order ki saaf peeli patti (`.co-why`):
  wajah + "Back to cart" link. Button JS se pehle ki tarah disabled
- Place Order ki sticky patti: safe-area ke saath (bottom: 8px + inset)
- Change address button 44px, Save / Cancel address 48px, confirm popup ke Yes / No 48px
- Body ka neeche gap safe-area ke saath
- Checkout ke hisse (address, delivery, schedule, payment, coupon, summary) jaise the waise; naya sirf upar ki wajah wali patti

## Jo nahi chheda
- URL names, views, place_order / payment / stock / coupon / wallet logic, checkout aur cart ka JS
- {% t %} / language: Step 7 mein (nayi wajah wali patti LANG_CODE se English / Urdu hai, purane pattern jaisi)

## place_order.html
- Koi view / template is ko render nahi karta (poore project mein reference nahi mila), is liye isko haath nahi lagaya. Agar aap ise kahin istemal karte hain to bata dein.

## Dekhna hai (phone par, 320 / 360 / 390 px, English aur Urdu)
- Cart: qty + / - angootha aaram se dabe, Remove, neeche Total + Checkout patti (notch wale phone par kinare se na kate)
- Cart: band store / minimum order wala cart: patti mein wajah dikhe, button disabled
- Checkout: Place Order patti scroll mein neeche chipki rahe, band store par peeli patti, address change popup, confirm popup
- Hard refresh karein (naya CSS /static/css/shop_cart.css?v=1, shop_checkout.css?v=1)
- Tests: python manage.py test app.tests_suite.tests_shop_css app.tests_suite.tests_shop_menu
