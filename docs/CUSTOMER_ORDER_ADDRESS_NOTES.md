# Order ka address (order ke saath copy + pending mein badlav)

## Pehle masla
Order, rider, vendor sab `customer.address` (profile) dikhate the. Customer profile ka address badalta to purane / chalte order ka address bhi badal jata.

## Ab
- SaleOrder.delivery_address (naya, migration 0110): place_order par customer ka address order mein copy hota hai.
- SaleOrder.ship_address(): order ka address, na ho (purane orders) to customer ka address.
- SaleOrder.can_change_address(): sirf status 'pending'.
- Naya view change_order_address (`shop/order/<id>/address/`): customer sirf apne pending order ka address badal sakta hai; profile ka address nahi badalta; purana map pin (delivery_lat/lng) hata deta hai.
- Order detail page par pending order mein "Address badlein" form; store accept kare to form nahi aata.
- Rider (card, offer, batch nav), vendor orders, POS payload ab order ka address use karte hain.

## Dekhna hai
- `python manage.py migrate` (0110), phir `python manage.py test app.tests_suite.tests_order_address`.
- Order do, phir profile address badlo: rider/vendor ko purana order wala address dikhna chahiye.
- Pending order par address badlo; vendor accept kare to form gayab.
## Jo nahi hua
- Address badalne par delivery fee dobara nahi nikalti (area badle to fee alag ho sakti hai).
- Rider assign / accept ke baad badlav band hai (chat ya store se rabta).

## Update: fee dobara + store ko khabar
- app/customer/address_change.py: address badalne par delivery fee = purani fee - purane area ka extra + naye area ka extra
  (DeliveryArea.extra_fee; address text mein area ka naam dhoondha jata hai). Sirf jab `shop_distance_fee_enabled` ON ho.
  Free / Pro se maaf delivery wale order ki fee nahi badalti. Doori wala hissa nahi badalta (naya pin nahi hota).
- delivery_fee (aur agar advance_payment == purani fee ho to wo bhi) update; order.notes mein "ADDRESS CHANGED" line.
- Store ko in-app notification + vendor orders list mein "Customer ne address badla hai" note.
- Customer ko success message mein nayi fee dikhti hai.
- Test: tests_order_address (AddressChangeFeeTests). Migration koi nayi nahi.

## Update: naya pin + doori wali fee
- Order detail ke address form mein "📍 Pin my current location" (lat/lng form ke saath jate hain).
- Store per-km fee / max km rakhta ho (aur switch ON): pin zaroori; fee = compute_fee(base, per_km, free_km, naya distance, naye area ka extra) — checkout wala hi formula.
  Store ki hadd (max_delivery_km) se door ho to badlav reject.
- Pin ke baghair (per-km na ho) purana area-extra wala hisab; purana pin hata diya jata hai.
