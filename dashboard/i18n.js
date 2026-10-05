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
  function phase(account) {
    const stages = {
      removing: ['Fjerner konto', 'Venter på, at backup og login er stoppet sikkert.'],
      starting: ['Forbereder backup', 'Forbereder kontoens browserprofil.'],
      waiting_login: ['Afslutter login-browser', 'Venter på, at login-browseren frigiver kontoen.'],
      finishing: ['Gemmer backupresultat', 'Gemmer historik og sender eventuelle notifikationer.'],
      checking: ['Kontrollerer backup', 'Kontrollerer at katalogets lokale filer findes og ikke er tomme.'],
      indexing: ['Indekserer billeder og albums', 'Læser billeddatoer og albumtilknytninger fra Google Fotos.'],
      organizing: ['Organiserer filer', 'Placering og albumreferencer opdateres på serveren.'],
      downloading: ['Henter billeder og videoer', 'Mediefiler hentes fra Google Fotos og organiseres løbende.'],
      stopping: ['Afbryder backup', 'Venter på, at kontoens processer afsluttes.']
    };
    const stage = stages[account.phase];
    if (!stage) return null;
    let detail = t(stage[1]);
    if (account.phase === 'indexing' && Number.isInteger(account.indexed_items)) {
      const format = n => new Intl.NumberFormat(language === 'da' ? 'da-DK' : 'en-GB').format(n);
      detail = format(account.indexed_items) + t(' indekserede billeder · ') + format(account.indexed_albums || 0) + t(' albums');
    }
    return {title: t(stage[0]), detail};
  }
  return {t, phase, locale: () => language === 'da' ? 'da-DK' : 'en-GB', set};
})();

