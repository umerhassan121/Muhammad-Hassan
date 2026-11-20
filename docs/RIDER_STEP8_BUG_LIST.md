# Rider portal - Step 8: Phone test ki Bugs ki list (web + APK)

Tareekh: 16 Nov 2026. Is step mein code nahi badla gaya (plan ke mutabiq Step 8 = sirf test aur list). Bugs Step 9 mein theek hongi.

## Test kaise hua (zaroori baat)
Asal phone / APK yahan nahi chal sakta. Is liye:
- Rider ke asal templates (base, menu, home, order card, SOS, location) ko Chromium mein **320x568, 360x640, 390x844 (iPhone notch)** screen par kholkar English aur Urdu dono mein naapa gaya. Tool: `scripts/checks_and_tests/rider_step8_phone_check.py`, nateeja `docs/step8_phone_check_output.txt`, screenshots `docs/step8_screens/`.
- APK ki files (`android_assets/rider_actions/*.java.txt`, `order_ring.wav`) aur `.github/workflows/deploy.yml` ka APK hissa **code padh kar** dekha. Awaaz, background GPS, back button **phone par hi confirm honge** (neeche checklist).
- Sirf Home page naapa gaya. Baqi pages ka sirf code scan hua (koi chhota checkbox/radio nahi mila).

## Jo theek nikla
- Home par har button / switch / More sheet ka link 44px se bara hai (sirf header ke language links chhote hain, neeche W2).
- Neeche ki bar 57px (iPhone par 91px), 5 tab mein naam nahi kat-te (English aur Urdu dono).
- SOS button bar se nahi takrata; More sheet SOS ke upar aati hai.
- Koi page side-scroll nahi karta.
- Naye order ke popup mein ACCEPT (60px) 320x568 par bhi bina scroll nazar aata hai.
- APK: service/receiver `exported=false` hain, ring 28 sec ki `order_ring.wav` (16kHz mono) theek hai, location/notification permissions workflow mein hain.

## Bugs (web)
| # | Darja | Masla | Kahan | Step 9 ka hal |
|---|---|---|---|---|
| W1 | **Bara** | GPS band / internet band ki patti upar fixed hoti hai aur **header ko dhaank leti hai**: language links aur Online switch dab nahi sakte. iPhone par patti 105px, switch poora dhak jata hai. GPS band ho to patti poore session mein rehti hai. (screenshot: `android-360x640-en-gps-bar.png`) | `rider.css .r-bars`, `rider_ux.js` | Patti ko normal flow mein ya `position:sticky` karna taake neeche ka content khisak jaye |
| W2 | Darmiyana | Header ke language links 65x21 aur 41x22 px (44 se chhote) | `components/lang_switch.html` (rider mein) | Rider header ke liye min-height 44px wala style |
| W3 | Darmiyana | Naya order aane par Home 1.5 sec baad `location.reload()` karta hai: rider ne jo **Delivery/Pickup code, photo, note** likha tha wo mit jata hai, "More actions" band ho jata hai. Popup band hone par bhi reload | `base.html` poll / `closeAlert` | Agar koi input mein likha ho ya form khula ho to reload na karein, "Naya order - dekhein" ki patti dikhayen |
| W4 | Darmiyana | SOS button aakhri card ke **Reject / Delivered** button ke daayen hisse par aa baithta hai (page ke aakhir par scroll nahi ho sakta). iPhone par `body padding-bottom:84px` bar (91px) se kam hai: aakhri 7px bar ke peeche | `rider.css .sosfab, body` | `padding-bottom: calc(140px + safe-area)` jab SOS on ho |
| W5 | Halka | "No internet - saving location" ki patti SOS ke neeche aa jati hai (patti ka daayan hissa chhup jata hai) | `_live_location.html chip()` | Patti ka right margin 72px ya SOS ke upar |
| W6 | Darmiyana | Popup ke ACCEPT / Reject / Later: spinner nahi, dobara dabne se bachao nahi, internet band ho to browser ka error page khulta hai (Step 7 ka guard sirf `submit` event par hai, popup `f.submit()` se bhejta hai) | `base.html post()` | `navigator.onLine` check + toast + buttons disable |
| W7 | Darmiyana (phone par dekhna) | `.top` header aur purana `.toast` mein `safe-area-inset-top` nahi. Notch wale iPhone (PWA) ya Android 15 edge-to-edge APK (Capacitor 7) mein naam / switch status bar ke neeche ja sakta hai | `rider.css .top, .toast` | `padding-top: calc(14px + env(safe-area-inset-top))` |
| W8 | Darmiyana | **Urdu rider ko kuch English**: popup ("NEW ORDER #..", "3 item(s) - From store - COD Rs.." number wale jumle dictionary se match nahi hote), "Delivered" ka `confirm()` sawal, location ki patti aur "Location permission is needed" dialog. `rider_i18n_audit.py` sirf HTML dekhta hai, JS strings nahi | `base.html`, `_act_deliver.html`, `_live_location.html` | JS ke jumle `{% t %}` se page par daal kar JS mein lena |
| W9 | Halka | Urdu / RTL: `.stops`, `.oc .items .row` mein `padding-left` (RTL mein ghalat taraf), Urdu bar ke labels 12px par bohat chhote, Urdu mein COD pill 360px par kat jata hai (`android-360x640-ur-home-bottom.png`) | `rider.css` | `padding-inline-start`, Urdu mein label 13-14px, pill wrap |
| W10 | Halka | Do toast system: purana `.toast` (z-index 50) internet ki patti ke peeche chhup jata hai ("New order available" nazar nahi aata) | `base.html`, `rider.css` | Sab `riderUx.toast` se |
| W11 | Darmiyana | Back button: More sheet, SOS sheet, order popup back dabane par band nahi hote (sirf Esc). APK mein `@capacitor/app` plugin hi nahi, to back = pichla page ya app band | `_rider_menu.html`, `base.html`, `deploy.yml` | `history.pushState` se sheets back par band karna; ya App plugin |
| W12 | Darmiyana | Live location: (a) APK mein background plugin fail ho to web GPS par **wapas nahi jata**, kuch bhi nahi bheja jata aur koi patti nahi; (b) Battery saver APK mein sirf bhejna kam karta hai, GPS power kam nahi hoti, jabke Settings mein likha hai "less GPS power"; (c) "Auto" saver iPhone par kaam nahi karta (`getBattery` nahi); (d) session khatam ho to server login page (200) deta hai aur code isay "bhej diya" samajh kar queue saaf kar deta hai; (e) location tab shuru hoti hai jab page load ho, order milne par rider kisi aur page par ho to rukti hai | `_live_location.html` | (a) fallback + patti, (b) Settings ka text sahi, (d) redirect pehchan kar patti |
| W13 | Phone par dekhna | Awaaz: web beep ke liye pehle ek touch zaroori; WebView ki autoplay policy confirm nahi. App khuli ho to push ki 28 sec ring aur popup ki beep **dono** baj sakti hain | `base.html beep()`, `RiderMessagingService` | Phone test se tay karein |

## Bugs / khatre (APK)
| # | Darja | Masla | Step 9 / aap |
|---|---|---|---|
| A1 | Phone par dekhna | Ring ki awaaz `USAGE_NOTIFICATION` hai: phone silent / Do-Not-Disturb mein ring nahi bajegi. Channel `orders_v2` ki awaaz baad mein badal nahi sakti | Test: silent mode mein naya order. Chahiye to `USAGE_ALARM` + nayi channel id |
| A2 | Phone par dekhna | Lock screen par sirf heads-up notification (full-screen intent nahi) | Test: screen lock mein order |
| A3 | Halka | Notification ke Accept / Decline ke jawab ("Order accepted" ...) sirf English mein hain (`RiderActionReceiver.java`) | APK ki file badalni hogi (aap se poochh kar) |
| A4 | Darmiyana | `@capacitor/app` nahi => back button handle nahi (W11) | `deploy.yml` mein plugin jodna (aap se poochh kar) |
| A5 | Phone par dekhna | Background location: Android 11+ par "Allow all the time" Settings se dena parta hai; sawal wala dialog English hai (W8). Foreground service ki notification "Rider online" English | Test + Urdu text |
| A6 | Phone par dekhna | Edge-to-edge (Android 15) par header / bar safe-area (W7) | Test: Android 15 phone |

Note: web ke badlav APK mein tab dikhte hain jab APK server se page kholta hai (`server.url`), ye abhi aise hi hai. W4, W6, W11 jaise badlav sirf web ke hain, APK dobara banane ki zaroorat nahi. A1, A3, A4 ke liye APK dobara banana parega.

## Aap ke phone par test ki checklist (10 minute)
1. Zip rakh kar server chalayein, rider se login. Header mein Online switch aur language links ek haath se dab rahe hain?
2. Phone ki location band karke app kholein: patti aati hai, Online switch phir bhi dabta hai? (W1)
3. Delivery code ka box bharein, doosre phone se naya order bhejein: kya likha hua mit gaya? (W3)
4. Home ke aakhir tak scroll karein: SOS aakhri button ko dhaanp raha hai? (W4)
5. Naya order aate hi: popup + awaaz. Phone silent mode mein bhi try karein. App khuli ho to awaaz do baar aayi? (W13, A1)
6. Popup mein internet band karke ACCEPT dabayein. (W6)
7. Lock screen par naya order notification + Accept button. (A2)
8. Active order ke sath app minimize / screen lock karke 2 minute chalayein: admin ko location update ja rahi hai? (A5)
9. Android back button: More sheet khuli ho to dabayein; Home par dabayein. (W11)
10. Urdu mein Home, popup, "Delivered" ka sawal dekhein: koi English reh gayi? (W8)
Bhej dein: jo kharab ho uska screenshot, aur phone ka model + Android version.
