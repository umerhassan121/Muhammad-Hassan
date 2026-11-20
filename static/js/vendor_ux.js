/* Vendor portal Step 7: loading nishan, offline patti, saaf error message.
   Har vendor page par _vendor_nav.html se load hota hai. */
(function () {
  'use strict';
  if (window.vendorUx) { return; }
  var ur = (document.documentElement.lang || '').toLowerCase().indexOf('ur') === 0;
  var T = {
    offline: ur ? 'انٹرنیٹ نہیں ہے۔ کنکشن چیک کریں۔' : 'No internet connection. Please check your connection.',
    online: ur ? 'انٹرنیٹ واپس آ گیا۔' : 'You are back online.',
    failed: ur ? 'کچھ غلط ہو گیا۔ دوبارہ کوشش کریں۔' : 'Something went wrong. Please try again.',
    sending: ur ? 'بھیجا جا رہا ہے…' : 'Sending…'
  };

  var bar = document.createElement('div');
  bar.className = 'v-offline';
  bar.setAttribute('role', 'alert');
  bar.textContent = T.offline;
  var toast = document.createElement('div');
  toast.className = 'v-toast';
  toast.setAttribute('role', 'status');
  document.addEventListener('DOMContentLoaded', function () {
    document.body.appendChild(bar);
    document.body.appendChild(toast);
    if (navigator.onLine === false) { bar.classList.add('is-on'); }
  });

  var toastTimer = null;
  function showToast(msg, isError) {
    if (!toast.parentNode) { return; }
    toast.textContent = msg;
    toast.className = 'v-toast is-on' + (isError ? ' v-toast--error' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove('is-on'); }, 4000);
  }

  window.addEventListener('offline', function () { bar.classList.add('is-on'); });
  window.addEventListener('online', function () { bar.classList.remove('is-on'); showToast(T.online, false); });

  // Form submit: button par spinner + dobara dabne se bachao. Back dabane par wapas normal.
  function resetLoading() {
    document.querySelectorAll('.is-loading').forEach(function (b) {
      b.classList.remove('is-loading');
      b.disabled = false;
      if (b.dataset.vOrigText) { b.textContent = b.dataset.vOrigText; delete b.dataset.vOrigText; }
    });
  }
  window.addEventListener('pageshow', resetLoading);

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || form.tagName !== 'FORM' || form.hasAttribute('data-no-loading') || e.defaultPrevented) { return; }
    if (navigator.onLine === false) {
      e.preventDefault();
      showToast(T.offline, true);
      return;
    }
    var btn = e.submitter || form.querySelector('button[type="submit"], input[type="submit"]');
    if (!btn || btn.classList.contains('is-loading')) {
      if (btn) { e.preventDefault(); }
      return;
    }
    // disable baad mein: pehle form ka data ja chuka hota hai (submitter ka name/value kho na jaye)
    setTimeout(function () {
      btn.classList.add('is-loading');
      btn.disabled = true;
    }, 0);
    // 20 second ke baad bhi jawab na aaye to button wapas kholo + message
    setTimeout(function () {
      if (btn.classList.contains('is-loading')) { resetLoading(); showToast(T.failed, true); }
    }, 20000);
  }, false);   // bubble: confirm() cancel hone par defaultPrevented sahi milta hai

  // Number wale inputs par phone ka number keyboard (decimal agar step poora number nahi)
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('input[type="number"]:not([inputmode])').forEach(function (i) {
      var st = i.getAttribute('step');
      i.setAttribute('inputmode', (st && st !== '1' && st !== 'any' && /\./.test(st)) || st === 'any' ? 'decimal' : 'numeric');
    });
  });

  // JS fetch wale kaam: error ek jaisa dikhane ke liye
  window.vendorUx = {
    toast: showToast,
    error: function (msg) { showToast(msg || T.failed, true); },
    text: T
  };
})();
