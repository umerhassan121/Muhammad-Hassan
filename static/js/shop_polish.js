/* Shop polish (v10): URL se # hatana (16) + image skeleton (14). Vendor pages par load nahi hota. */
(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var isHome = /^\/shop\/?$/.test(location.pathname);

  /* ---- 16. In-page link (#products-section, #deals) URL mein # nahi chhodte ---- */
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[href^="#"]') : null;
    if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.button) { return; }
    var names = a.getAttributeNames ? a.getAttributeNames() : [];
    for (var i = 0; i < names.length; i++) { if (names[i].indexOf('data-bs') === 0) { return; } }
    if (a.getAttribute('role') === 'tab') { return; }
    var id = a.getAttribute('href').slice(1);
    if (!id) { if (isHome) { e.preventDefault(); } return; }
    var el = document.getElementById(id);
    if (!el || !isHome) { return; }
    e.preventDefault();
    el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  });
  function cleanHash() {
    if (!isHome || !location.hash || !window.history || !history.replaceState) { return; }
    try { history.replaceState(history.state, '', location.pathname + location.search); } catch (err) {}
  }
  window.addEventListener('load', function () { setTimeout(cleanHash, 60); });
  window.addEventListener('hashchange', function () { setTimeout(cleanHash, 0); });

  /* ---- 14. Skeleton: lazy images ke peeche chamak, image aate hi fade-in ---- */
  function done(img) {
    img.classList.add('is-loaded');
    if (img.parentElement) { img.parentElement.classList.remove('sk-on'); }
  }
  function prep(img) {
    if (img.classList.contains('sk-img') || img.complete) { return; }
    img.classList.add('sk-img');
    if (img.parentElement) { img.parentElement.classList.add('sk-on'); }
    img.addEventListener('load', function () { done(img); }, { once: true });
    img.addEventListener('error', function () { done(img); }, { once: true });
    setTimeout(function () { done(img); }, 8000);   // kisi wajah se event na aaye to image chhupi na rahe
  }
  function scan() {
    var list = document.querySelectorAll('.product-image img, .promo-img img, .store-card img, .stl img');
    for (var i = 0; i < list.length; i++) { prep(list[i]); }
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', scan); } else { scan(); }
})();
