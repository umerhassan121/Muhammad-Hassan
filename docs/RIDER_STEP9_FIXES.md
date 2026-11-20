# Rider portal - Step 9: Step 8 ki bugs ka fix

Test: `python3 scripts/checks_and_tests/rider_step8_phone_check.py` (nateeja `docs/step9_phone_check_output.txt`). Django yahan nahi chala, is liye `python manage.py test app.tests_suite.tests_rider_language` aap ke server par chalayein (naya `RiderStep9Files` class jura hai).

## Theek ho gaya (browser mein naap kar confirm)
- W1 GPS / internet ki patti ab content ko neeche khisakti hai, Online switch aur language links nahi dhakti (`rider.css`, `rider_ux.js`)
- W2 header ke language links ab 44px
- W3 naya order aane par page reload tab tak nahi hota jab rider kuch likh raha ho ya "More actions" khula ho (`riderUx.reloadWhenIdle`)
- W4 SOS aakhri button ko nahi dhakta (`body.has-sos`), iPhone par bar ke liye jagah
- W5 location ki patti SOS se nahi takrati
- W6 popup: internet band ho to toast, dabne ke baad sab button band + spinner
- W7 header aur toast mein safe-area (notch)
- W8 popup, location patti, "Delivered" confirm, location permission dialog ab Urdu mein (rider_step6.py)
- W9 RTL padding, Urdu bar labels 13px, COD pill kat-ta nahi
- W10 purana toast ab `riderUx.toast` se
- W11 Android back button More sheet / SOS sheet band karta hai (page se bahar nahi nikalta)
- W12 (a) APK plugin fail ho to web GPS par wapas, (b) Settings ka text sahi, (d) session khatam ho to patti aur queue safe

## Baqi (phone par ya APK se)
- W12(c) iPhone par Auto battery saver nahi chalta (browser ki hadd). W12(e) order milne par rider kisi aur page par ho to location agle page load par shuru hoti hai (navigate.html ko chhune se bachne ke liye chhora).
- W13, A1, A2, A5, A6: awaaz, silent mode, lock screen, background GPS, Android 15 safe-area: sirf phone par dekhe ja sakte hain.
- A3 (notification ke jawab English) aur A4 (`@capacitor/app` plugin, popup par back) ke liye APK ka build badalna parega: aap se poochh kar.

Web fixes APK mein tab dikhte hain jab APK server se page kholta hai (abhi aisa hi hai).

## Step 9 ka baqi kaam (16 Nov 2026, dusri dafa)
- W11 (popup): back button ab order popup ko "Later" ki tarah band karta hai (`base.html`, `riderUx.trap('offer')`). ACCEPT / Reject par history mein extra entry nahi bachti. Browser mein naap kar confirm: `popup_back_closes`, `popup_later_keeps_history_clean` (`docs/step9_phone_check_output.txt`).
- A3: notification ke Accept / Decline ka jawab ab rider ki language mein. APK ka receiver WebView cookie (`erp_lang`) se language leta hai, server ko `lang` bhejta hai, aur server (`push_actions.py`) message Urdu mein lauta-ta hai; internet band wala message aur title bhi Urdu (`RiderActionReceiver.java.txt`, `rider_step6.py`). **APK dobara banana parega.**
- A4: rider APK mein `@capacitor/app@^7` jura (`deploy.yml`) aur `rider_ux.js` mein back handler: sheet / popup khuli ho to band, warna pichla page, Home par app minimize (rider online / location chalti rahe). **APK dobara banana parega.** Plugin ke baghair (purana APK) kuch nahi badalta.
- Naye tests: `RiderStep9Files` mein 3 test jure. Django yahan nahi chala: `python manage.py test app.tests_suite.tests_rider_language` apne server par chalayein.

## Ab bhi sirf phone par dekhna / aap ke faisle par
- W13, A1 (silent mode mein ring: `USAGE_ALARM` + nayi channel id ka faisla aap ka), A2 (lock screen), A5 (background GPS "Allow all the time", foreground notification ka English text), A6 (Android 15 safe-area): checklist `docs/RIDER_STEP8_BUG_LIST.md` ke mutabiq phone par.
- W12(c) iPhone par Auto battery saver (browser ki hadd), W12(e) order milne par rider kisi aur page par ho to location agle page se shuru.
- Admin pages ke 8 untranslated jumle (`peak_admin`, `shift_admin`, `manage`, `_nav_screen` ka "km/h") plan se bahar hain.
