/* Rider portal Step 7 (+ Step 9 fixes): internet / GPS ki patti, loading nishan, dobara dabne se bachao, saaf error.
   rider/base.html se har rider page par load hota hai. Urdu / English page ki language (html lang) se.
   Urdu text mein ' (single quote) na likhein. */
(function () {
  'use strict';
  if (window.riderUx) { return; }
  var ur = (document.documentElement.lang || '').toLowerCase().indexOf('ur') === 0;
  var T = {
    offline: ur ? 'انٹرنیٹ بند ہے۔ اپنا کنکشن چیک کریں۔' : 'No internet connection. Please check your connection.',
    weak: ur ? 'کنکشن کمزور ہے۔ دوبارہ جڑنے کی کوشش ہو رہی ہے۔' : 'Weak connection. Trying to reconnect.',
    online: ur ? 'انٹرنیٹ واپس آ گیا۔' : 'You are back online.',
    failed: ur ? 'کچھ غلط ہو گیا۔ دوبارہ کوشش کریں۔' : 'Something went wrong. Please try again.',
    gpsDenied: ur ? 'لوکیشن بند ہے۔ آرڈر آپ تک پہنچانے کے لیے فون کی سیٹنگ میں لوکیشن آن کریں۔'
                  : 'Location is off for this app. Turn on location in your phone settings so orders can reach you.',
    session: ur ? 'سیشن ختم ہو گیا۔ دوبارہ لاگ ان کریں۔' : 'Your session has expired. Please log in again.',
    refresh: ur ? 'نیا آرڈر آیا ہے۔ جو لکھ رہے ہیں وہ مکمل کریں، پھر صفحہ خود تازہ ہو گا۔' : 'Something new came in. Finish what you are typing and the page will refresh.',
    gpsOff: ur ? 'لوکیشن نہیں مل رہی۔ GPS آن کریں اور کھلی جگہ آ جائیں۔'
               : 'Cannot find your location. Turn on GPS and move to an open area.'
  };

  var wrap = document.createElement('div');
  wrap.className = 'r-bars';
  var netBar = document.createElement('div');
  netBar.className = 'r-bar r-bar--bad';
  netBar.setAttribute('role', 'alert');
  var gpsBar = document.createElement('div');
  gpsBar.className = 'r-bar r-bar--warn';
  gpsBar.setAttribute('role', 'alert');
  wrap.appendChild(netBar);
  wrap.appendChild(gpsBar);
  var toast = document.createElement('div');
  toast.className = 'r-toast';
  toast.setAttribute('role', 'status');

  var fails = 0;
  function showNet(text) { netBar.textContent = text; netBar.classList.add('is-on'); }
  function hideNet() { netBar.classList.remove('is-on'); }
  function refreshNet() {
    if (navigator.onLine === false) { showNet(T.offline); }
    else if (fails >= 2) { showNet(T.weak); }
    else { hideNet(); }
  }

  var toastTimer = null;
  function showToast(msg, isError) {
    if (!toast.parentNode) { return; }
    toast.textContent = msg;
    toast.className = 'r-toast is-on' + (isError ? ' r-toast--error' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove('is-on'); }, 4000);
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.body.insertBefore(wrap, document.body.firstChild);   // sab se upar, normal flow mein (content dhakta nahi)
    document.body.appendChild(toast);
    refreshNet();
  });
  window.addEventListener('offline', refreshNet);
  window.addEventListener('online', function () { fails = 0; refreshNet(); showToast(T.online, false); });

  // Button par spinner + dobara dabne se bachao. Back dabane par (pageshow) sab wapas normal.
  function resetLoading() {
    document.querySelectorAll('.is-loading').forEach(function (b) {
      b.classList.remove('is-loading');
      b.disabled = false;
    });
  }
  window.addEventListener('pageshow', resetLoading);

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || form.tagName !== 'FORM' || form.hasAttribute('data-no-loading') || e.defaultPrevented) { return; }
    if (navigator.onLine === false) {          // internet nahi: form na jaye, saaf message mile
      e.preventDefault();
      showToast(T.offline, true);
      return;
    }
    var btn = e.submitter || form.querySelector('button[type="submit"], button:not([type]), input[type="submit"]');
    if (!btn || btn.classList.contains('is-loading')) {
      if (btn) { e.preventDefault(); }
      return;
    }
    // disable baad mein: pehle form ka data ja chuka hota hai (button ka name/value kho na jaye)
    setTimeout(function () { btn.classList.add('is-loading'); btn.disabled = true; }, 0);
    var wait = form.querySelector('input[type="file"]') ? 90000 : 20000;      // photo upload mein zyada waqt
    setTimeout(function () {
      if (btn.classList.contains('is-loading')) { resetLoading(); showToast(T.failed, true); }
    }, wait);
  }, false);

  // Number wale inputs par phone ka number keyboard
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('input[type="number"]:not([inputmode])').forEach(function (i) {
      var st = i.getAttribute('step');
      i.setAttribute('inputmode', (st && st !== '1' && /\./.test(st)) || st === 'any' ? 'decimal' : 'numeric');
    });
  });

  // ---- Step 9 (W3): page tab tak reload na ho jab rider kuch likh raha ho (code, photo, note) ----
  function busyTyping() {
    var a = document.activeElement;
    if (a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) && a.type !== 'hidden' && a.type !== 'button' && a.type !== 'submit') { return true; }
    if (document.querySelector('details.moreact[open], details.sub[open], details.skip[open]')) { return true; }
    var f = document.querySelectorAll('input[type="text"], input[type="file"], input[type="password"], input[type="tel"], textarea');
    for (var i = 0; i < f.length; i++) { if (f[i].value && f[i].offsetParent !== null && !f[i].closest('#offerAlert')) { return true; } }
    return false;
  }
  var reloadTimer = null, told = false;
  function reloadWhenIdle(delay) {
    if (reloadTimer) { return; }
    reloadTimer = setTimeout(function tryReload() {
      if (busyTyping()) {
        if (!told) { told = true; showToast(T.refresh, false); }
        reloadTimer = setTimeout(tryReload, 5000);
        return;
      }
      location.reload();
    }, delay || 0);
  }

  // ---- Step 9 (W11): Android back button sheet ko band kare (page se bahar na nikle) ----
  // t = riderUx.trap('key', function(){ ...band karo... });  UI se band karna: t.close();  link / form par jana: t.leave(function(){ location.href = ... })
  function trap(key, closeFn) {
    var live = true;
    try { history.pushState({rtrap: key}, ''); } catch (e) { return {close: closeFn, leave: function (fn) { fn(); }}; }
    function onpop() { if (!live) { return; } live = false; window.removeEventListener('popstate', onpop); closeFn(); }
    window.addEventListener('popstate', onpop);
    function mine() { return history.state && history.state.rtrap === key; }
    return {
      close: function () {
        if (!live) { return; }
        if (mine()) { history.back(); } else { live = false; window.removeEventListener('popstate', onpop); closeFn(); }
      },
      leave: function (fn) {
        if (!live || !mine()) { fn(); return; }
        live = false; window.removeEventListener('popstate', onpop);
        window.addEventListener('popstate', function once() { window.removeEventListener('popstate', once); fn(); });
        history.back();
      }
    };
  }

  window.riderUx = {
    reloadWhenIdle: reloadWhenIdle,
    busyTyping: busyTyping,
    trap: trap,
    isOnline: function () { return navigator.onLine !== false; },
    toast: showToast,
    error: function (msg) { showToast(msg || T.failed, true); },
    // JS fetch wale button ke liye: riderUx.busy(btn, true) ... riderUx.busy(btn, false)
    busy: function (btn, on) {
      if (!btn) { return; }
      btn.classList.toggle('is-loading', !!on);
      btn.disabled = !!on;
    },
    // rider/base.html ka poll: do baar lagataar fail ho to "kamzor connection" patti
    pollOk: function () { if (fails) { fails = 0; refreshNet(); } },
    pollFailed: function () { fails += 1; refreshNet(); },
    // GPS: 'ok' | 'denied' | 'off'
    gps: function (state) {
      if (state === 'denied') { gpsBar.textContent = T.gpsDenied; gpsBar.classList.add('is-on'); }
      else if (state === 'off') { gpsBar.textContent = T.gpsOff; gpsBar.classList.add('is-on'); }
      else { gpsBar.classList.remove('is-on'); }
    },
    text: T
  };

  // ---- Step 9 (A4): APK ka back button (sirf jab @capacitor/app plugin APK mein ho; browser mein kuch nahi hota) ----
  // Sheet / popup khuli ho to wo band hoti hai (trap), warna pichla page; Home par app minimize (rider online / location chalti rahe, app band na ho).
  try {
    var capApp = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.App;
    if (capApp && capApp.addListener) {
      capApp.addListener('backButton', function (ev) {
        if (history.state && history.state.rtrap) { history.back(); return; }
        if (ev && ev.canGoBack) { history.back(); return; }
        if (capApp.minimizeApp) { capApp.minimizeApp(); } else if (capApp.exitApp) { capApp.exitApp(); }
      });
    }
  } catch (e) { /* plugin nahi: WebView ka apna back chalega */ }
})();
