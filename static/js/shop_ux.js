/* Customer portal Step 8: internet patti, toast, button spinner, dobara dabne se bachao, saaf fetch errors.
   base_shop.html se load hota hai (vendor pages par nahi: un ka apna vendor_ux.js hai). */
(function () {
  'use strict';
  if (window.shopUx) { return; }
  var ur = (document.documentElement.lang || '').toLowerCase().indexOf('ur') === 0;
  var T = {
    offline: ur ? 'انٹرنیٹ نہیں ہے۔ کنکشن چیک کریں۔' : 'No internet connection. Please check your connection.',
    online: ur ? 'انٹرنیٹ واپس آ گیا۔' : 'You are back online.',
    failed: ur ? 'کچھ غلط ہو گیا۔ دوبارہ کوشش کریں۔' : 'Something went wrong. Please try again.',
    timeout: ur ? 'جواب میں دیر ہو رہی ہے۔ دوبارہ کوشش کریں۔' : 'This is taking too long. Please try again.',
    session: ur ? 'سیشن ختم ہو گیا۔ دوبارہ لاگ اِن کریں۔' : 'Your session has ended. Please log in again.',
    server: ur ? 'سرور میں مسئلہ ہے۔ تھوڑی دیر بعد کوشش کریں۔' : 'Server problem. Please try again in a moment.',
    notfound: ur ? 'یہ صفحہ یا چیز نہیں ملی۔' : 'This page or item was not found.',
    unsure: ur ? 'آرڈر کی تصدیق نہیں ہوئی۔ دوبارہ بھیجنے سے پہلے "میرے آرڈرز" دیکھ لیں۔'
               : 'We could not confirm your order. Check My Orders before sending it again.'
  };

  // ---------- offline patti (normal flow: header / bar / chat button ko nahi dhaanpti) ----------
  var bar = document.createElement('div');
  bar.className = 's-offline';
  bar.setAttribute('role', 'alert');
  bar.textContent = T.offline;
  var toast = document.createElement('div');
  toast.className = 's-toast';
  toast.setAttribute('role', 'status');
  toast.setAttribute('aria-live', 'polite');

  function mount() {
    if (!bar.parentNode) { document.body.insertBefore(bar, document.body.firstChild); }
    if (!toast.parentNode) { document.body.appendChild(toast); }
    if (navigator.onLine === false) { bar.classList.add('is-on'); }
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', mount); } else { mount(); }

  var toastTimer = null;
  function showToast(msg, isError) {
    mount();
    toast.textContent = msg;
    toast.className = 's-toast is-on' + (isError ? ' s-toast--error' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove('is-on'); }, 4200);
  }

  window.addEventListener('offline', function () { mount(); bar.classList.add('is-on'); });
  window.addEventListener('online', function () { bar.classList.remove('is-on'); showToast(T.online, false); });

  // ---------- form submit: spinner + dobara dabne se bachao ----------
  function resetLoading() {
    document.querySelectorAll('.is-loading').forEach(function (b) {
      b.classList.remove('is-loading');
      b.disabled = false;
    });
  }
  window.addEventListener('pageshow', resetLoading);   // Back dabane par button wapas normal

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || form.tagName !== 'FORM' || form.hasAttribute('data-no-loading') || e.defaultPrevented) { return; }
    if (navigator.onLine === false) {
      e.preventDefault();
      showToast(T.offline, true);
      return;
    }
    var btn = e.submitter || form.querySelector('button[type="submit"], input[type="submit"]');
    if (!btn) { return; }
    if (btn.classList.contains('is-loading')) { e.preventDefault(); return; }
    // disable baad mein: pehle form ka data ja chuka hota hai (submitter ka name/value kho na jaye)
    setTimeout(function () { btn.classList.add('is-loading'); btn.disabled = true; }, 0);
    // 20 second tak jawab na aaye to button wapas kholo
    setTimeout(function () {
      if (btn.classList.contains('is-loading')) { resetLoading(); showToast(T.timeout, true); }
    }, 20000);
  }, false);

  // Internet band ho to link browser ke error page par na jaye
  document.addEventListener('click', function (e) {
    if (navigator.onLine !== false) { return; }
    var a = e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || e.defaultPrevented) { return; }
    var href = a.getAttribute('href') || '';
    if (href.charAt(0) === '#' || href.indexOf('javascript:') === 0 || href.indexOf('tel:') === 0 ||
        href.indexOf('mailto:') === 0 || href.indexOf('https://wa.me') === 0 || a.hasAttribute('data-allow-offline')) { return; }
    e.preventDefault();
    showToast(T.offline, true);
  }, true);

  // ---------- fetch: har fail ko pehchano ----------
  // Result: {ok, kind, status, data, message}
  // kind: ok | offline | timeout | session | notfound | server | html | http
  // Order jaisi cheez par kind 'timeout' / 'network' = "shayad chala gaya" (unsure: true)
  function fetchJson(url, opts, timeoutMs) {
    opts = opts || {};
    opts.credentials = opts.credentials || 'same-origin';
    opts.headers = opts.headers || {};
    if (!opts.headers['X-Requested-With']) { opts.headers['X-Requested-With'] = 'XMLHttpRequest'; }
    if (navigator.onLine === false) {
      return Promise.resolve({ ok: false, kind: 'offline', status: 0, data: null, message: T.offline, unsure: false });
    }
    var ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    if (ctrl) { opts.signal = ctrl.signal; }
    var timedOut = false;
    var timer = setTimeout(function () { timedOut = true; if (ctrl) { ctrl.abort(); } }, timeoutMs || 25000);

    return fetch(url, opts).then(function (res) {
      clearTimeout(timer);
      var ct = (res.headers.get('content-type') || '').toLowerCase();
      if (res.status === 401 || res.status === 403 || (res.redirected && /login/i.test(res.url || ''))) {
        return { ok: false, kind: 'session', status: res.status, data: null, message: T.session, unsure: false };
      }
      if (res.status === 404) { return { ok: false, kind: 'notfound', status: 404, data: null, message: T.notfound, unsure: false }; }
      if (res.status >= 500) { return { ok: false, kind: 'server', status: res.status, data: null, message: T.server, unsure: true }; }
      if (ct.indexOf('json') === -1) {
        return { ok: false, kind: 'html', status: res.status, data: null, message: T.failed, unsure: true };
      }
      return res.json().then(function (d) {
        var good = res.ok;
        return { ok: good, kind: good ? 'ok' : 'http', status: res.status, data: d,
                 message: (d && d.message) || (good ? '' : T.failed), unsure: false };
      }, function () {
        return { ok: false, kind: 'html', status: res.status, data: null, message: T.failed, unsure: true };
      });
    }, function () {
      clearTimeout(timer);
      if (timedOut) { return { ok: false, kind: 'timeout', status: 0, data: null, message: T.timeout, unsure: true }; }
      if (navigator.onLine === false) { return { ok: false, kind: 'offline', status: 0, data: null, message: T.offline, unsure: true }; }
      return { ok: false, kind: 'network', status: 0, data: null, message: T.offline, unsure: true };
    });
  }

  // Button par spinner (JS wale kaam): shopUx.busy(btn, true/false)
  function busy(btn, on) {
    if (!btn) { return; }
    btn.classList.toggle('is-loading', !!on);
    btn.disabled = !!on;
  }

  window.shopUx = {
    toast: showToast,
    error: function (msg) { showToast(msg || T.failed, true); },
    // fetch .catch() ke liye: internet band ho to wohi batao, warna aam message
    netError: function () { showToast(navigator.onLine === false ? T.offline : T.failed, true); },
    ok: function (msg) { showToast(msg, false); },
    fetchJson: fetchJson,
    busy: busy,
    text: T
  };
})();
