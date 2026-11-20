# Customer Step 3 - Home aur Stores saaf

## Naya
- templates/customer_portal/_store_tile.html     : store ka ek card (Home aur Stores page dono)
- templates/customer_portal/_store_tile_css.html : us card ki CSS (Step 4 mein static/css/shop.css)

## Badla
### shop.html (Home)
- Header halka: bara "Premium Shopping / Welcome to ..." hissa hata diya (naam upar navbar mein hai). Ab: Deliver to + search.
- Info patti se "24/7 support" chip hata diya (baqi: ETA, Store pickup, Cash on delivery).
- "Stores near you": ab shared card `_store_tile.html` (pehle alag card tha).
- Product card:
  * bara "Add" button (44px unchi, poori chaurai), saath mein Buy Now ab 44x44 icon (feature wahi hai)
  * "In Stock" badge hata diya (sirf Low stock / Out of stock / Best Price / In Cart dikhte hain)
  * category/brand wali line sirf search ke waqt
  * "View Cart" aur "Out of Stock" button bhi 44px
  * add_to_cart ka JS nahi chheda
- "Deliver to" button 44px.

### stores.html
- Store card ab `_store_tile.html` (pehle st-card tha). Grid `.stl-grid`.
- Sab filter, search, banner, area note, favourite, sort jaise the waise.

### Store card ek jaise
- Cover + logo, ek hi flag: Closed > Busy > Free delivery.
- Naam, ek line (type / cuisine / city), offer / discount, rating (ya New), ETA, delivery fee (ya Free), min order, "Too far".
- Favourite button 44px tap area (sirf Stores page par, jahan favourites on hon).

## Jo nahi chheda
- URL names, view code, cart / order logic, search ka JS, voice search.
- Purani `.store-card` / `.st-card` CSS ab dead hai; Step 4 mein safai.
- `_store_card.html` (store detail ka product card, pehle se "Add" button wala) ko haath nahi lagaya; Step 6 mein store_detail ke saath.

## Dekhna hai (phone par)
- Home: header, categories, promo, Stores near you, product card par Add / Buy Now icon.
- Stores: card ek jaisa, favourite dil, filter.
- Stores page par Busy + Free delivery wala store: flag "Busy" dikhega, fee "Free" meta mein.
