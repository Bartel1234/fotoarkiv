'use strict';
// The catalog is injected before deferred scripts run by the dashboard server.
const I18n = (() => {
  const catalog = JSON.parse(document.getElementById('translation-catalog').textContent);
  let language = 'en';
  try { if (localStorage.getItem('fotoarkiv-language') === 'da') language = 'da'; } catch (_) {
    if (document.cookie.split('; ').includes('fotoarkiv_language=da')) language = 'da';
  }
  const t = key => language === 'da' ? key : (catalog[key] || key);
  function apply() {
    document.documentElement.lang = language;
    document.querySelectorAll('[data-i18n]').forEach(node => { node.textContent = t(node.dataset.i18n); });
    for (const attr of ['title', 'placeholder', 'aria-label']) {
      document.querySelectorAll('[data-i18n-' + attr + ']').forEach(node => {
        node.setAttribute(attr, t(node.getAttribute('data-i18n-' + attr)));
      });
    }
    document.querySelectorAll('[data-language]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.language === language));
    });
    document.cookie = 'fotoarkiv_language=' + language + '; Path=/; Max-Age=31536000; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : '');
  }
  function set(value) {
    if (value !== 'en' && value !== 'da') return;
    language = value;
    try { localStorage.setItem('fotoarkiv-language', value); } catch (_) {}
    apply();
    window.dispatchEvent(new Event('languagechange'));
  }
  document.querySelectorAll('[data-language]').forEach(button => button.addEventListener('click', () => set(button.dataset.language)));
  apply();
  return {t, locale: () => language === 'da' ? 'da-DK' : 'en-GB', set};
})();
