# Customer Step 9 - Phone test (Chromium 320 / 360 / 390 px, English + Urdu RTL)

Tool: python3 scripts/checks_and_tests/customer_step9_phone_check.py  (nateeja: docs/step9_customer_phone_check_output.json)
Asli templates (_shop_menu.html, _empty_state.html) + shop.css + shop_ux.js. 42 check: 42 pass.

## Check hue
- har tab / button / link 44px ya zyada (neeche ki bar, khali screen ke button, wajah wali patti ke button)
- horizontal scroll nahi; Urdu (RTL) mein bar ke labels kat te nahi
- chipakne wali patti (.pd-bar) neeche ki bar ke ooper; toast bar ke ooper
- internet ki patti header ko nahi dhaanpti

## Bugs / findings
| # | Masla | Haal |
|---|-------|------|
| 1 | Roman Urdu jo audit ki word-list se chhoot gaya: login "Password bhool gaye?", product note placeholder, checkout "Jaldi se jaldi" aur "ke liye schedule hoga", order detail "waqt khatam / baqi" | Theek (Step 10), audit ki list mein alfaz jode, test lagaya |
| 2 | chat_widget.html (floating chat button, bottom 24px) bar (z 1030) ke neeche dab jata | Abhi koi page isay include nahi karta, is liye asar nahi. Agar kabhi lagayein to bottom bar ke ooper karna hoga |
| 3 | place_order.html mein purane alert() | Koi view isay render nahi karta, nahi chheda |
| 4 | Tracking map / chat ke background poll chup-chap fail | Internet ki patti dikhati hai, nahi chheda |

## Sirf asal phone / APK par dekhna hai (yahan nahi ho sakta)
- notch / gesture bar (safe-area) asal phone par
- Android back button (sheet band ho, page wapas jaye)
- tracking map ka size aur live marker
- customer APK ka naya build aur push notification (Web badlav APK mein tab dikhte hain jab APK server se page khole)
- checkout par asal internet toot-na (order lagne ke bad jawab na aana)
- Django tests (server par): python manage.py test app.tests_suite.tests_customer_step8 app.tests_suite.tests_customer_language
