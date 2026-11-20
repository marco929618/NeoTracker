/* ============================================================================
   v_impostazioni.js - source of the UV index (Open-Meteo / OpenWeather), SkinSense, PubMed email, installation status
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  NT.viste.impostazioni = async function (cont) {
    [S.imp, S.stato] = await Promise.all([NT.get('/api/impostazioni'), NT.get('/api/stato')]);

    async function salva(parziale, messaggio) {
      try { S.imp = await NT.api('PUT', '/api/impostazioni', parziale); if (messaggio) NT.toast(messaggio, 'ok'); return true; }
      catch (e) { NT.errore(e); return false; }
    }

    /* ---------------- interface language ---------------- */
    // 'auto' = the system language; to apply the choice it saves and reloads the page
    const selLingua = h('select', { class: 'campo', id: 'sel-lingua', 'aria-label': NT.t('Interface language'),
      onchange: async () => { if (await salva({ lingua: selLingua.value })) location.reload(); else selLingua.value = NT.linguaScelta; } },
      h('option', { value: 'auto' }, NT.t('Automatic (same as the system)')),
      NT.LINGUE.map(l => h('option', { value: l[0] }, l[1])));
    selLingua.value = NT.linguaScelta;
    const sezLingua = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Language')),
      h('label', { for: 'sel-lingua', class: 'blocco' }, NT.t('Interface language')), selLingua,
      h('p', { class: 'piccolo muted' }, NT.t('The choice applies to all users of this computer. The original and binding text of the legal notices is the English one; the full text report stays in English.')));

    /* ---------------- UV index: data source ---------------- */
    const esitoProva = h('div', { class: 'prova-esito', role: 'status' });
    const campoChiave = h('input', { type: 'password', class: 'campo', autocomplete: 'off', spellcheck: 'false', maxlength: 64,
      placeholder: '', 'aria-label': NT.t('OpenWeather key') });
    const segnapostoChiave = () => S.imp.ha_chiave_owm ? NT.t('Key saved ({finale}) — type a new one to replace it', { finale: S.imp.chiave_owm_finale }) : NT.t('Paste the key here (32 letters and digits)');
    campoChiave.placeholder = segnapostoChiave();
    const sezOWM = h('section', { class: 'scheda' });
    function disegnaOWM() {
      campoChiave.placeholder = segnapostoChiave();
      const ow = S.imp.fonte_uv === 'openweather';
      // a row with a dot: choosing changes the source at once and redraws the section
      const scelta = (valore, titolo, desc) => h('label', { class: 'riga-inline' },
        h('input', { type: 'radio', name: 'fonte-uv', value: valore, checked: S.imp.fonte_uv === valore,
          onchange: async () => { if (await salva({ fonte_uv: valore }, NT.t('UV index source changed.'))) { NT.riempi(esitoProva); disegnaOWM(); } } }),
        h('span', {}, h('strong', {}, titolo), ' ', h('span', { class: 'piccolo muted' }, desc)));
      NT.riempi(sezOWM, h('h2', {}, NT.t('UV index: data source')),
        scelta('open-meteo', NT.t('Open-Meteo (default)'), NT.t('free, no account or key needed')),
        scelta('openweather', 'OpenWeather', NT.t('optional: requires a personal key of your own')),
        !ow ? h('p', { class: 'piccolo muted' }, NT.t('Weather and UV data:') + ' ', NT.link('https://open-meteo.com/', 'Open-Meteo.com'), ' ' + NT.t('(CC BY 4.0 licence). The free service is for personal, non-commercial use.') + ' ',
          NT.t('City search also uses Open-Meteo.')) : null,
        ow ? h('div', { class: 'banda ' + (S.imp.ha_chiave_owm ? 'verde' : 'giallo') }, S.imp.ha_chiave_owm ? NT.t('OpenWeather key saved ({finale}).', { finale: S.imp.chiave_owm_finale }) : NT.t('You chose OpenWeather but there is no key yet: until one is added, the program uses Open-Meteo.')) : null,
        ow ? h('div', { class: 'riga-inline' }, campoChiave,
          h('button', { class: 'btn btn-pri', onclick: async () => { const k = campoChiave.value.trim(); if (!k) { NT.toast(NT.t('Paste the key first.'), 'errore'); return; } if (await salva({ openweather_key: k }, NT.t('Key saved.'))) { campoChiave.value = ''; NT.riempi(esitoProva); disegnaOWM(); } } }, NT.t('Save')),
          S.imp.ha_chiave_owm ? h('button', { class: 'btn', onclick: provaChiave }, NT.t('Test the key')) : null,
          S.imp.ha_chiave_owm ? h('button', { class: 'btn-testo pericolo', onclick: async () => { if (await NT.conferma(NT.t('Remove the key?'), NT.t('The key will be deleted from this computer. You can enter it again whenever you want.'), { si: NT.t('Remove'), pericolo: true }) && await salva({ openweather_key: '' }, NT.t('Key removed.'))) { NT.riempi(esitoProva); disegnaOWM(); } } }, NT.t('Remove')) : null) : null,
        ow ? esitoProva : null,
        ow ? h('details', { class: 'abstract' }, h('summary', {}, NT.t('How to get the key')),
          h('ol', { class: 'passi' },
            h('li', {}, NT.t('Create a free account at') + ' ', NT.link('https://home.openweathermap.org/users/sign_up', 'openweathermap.org'), ' ' + NT.t('and confirm the email.')),
            h('li', {}, NT.t('Open the «API keys» page of your account and copy the key.')),
            h('li', {}, NT.t('Subscribe to the pay-per-call «One Call API» plan') + ' (', NT.link('https://openweathermap.org/api/one-call-4', NT.t('service page')), '): ' + NT.t('the first 1,000 calls per day are free, later ones are charged. OpenWeather may ask for a payment card to activate it: check the conditions on their website.')),
            h('li', {}, NT.t('When you subscribe, the default daily limit is 2,000 calls: in the «Billing plans» tab of your account you can lower it to 1,000, so you spend nothing. NeoTracker uses very few (at most 4 every 10 minutes, only when you open the UV Index page).')),
            h('li', {}, NT.t('Paste the key above and press «Test the key». After subscribing, the key can take a few minutes to activate. The program tries One Call 4.0 first and, if the key belongs to an older plan, One Call 3.0.'))),
          h('p', { class: 'piccolo muted' }, NT.t("The key stays saved only on your computer and is never shown to, or sent to, the program's web page: the Python program uses it to call OpenWeather."))) : null);
    }
    async function provaChiave() {
      NT.riempi(esitoProva, NT.caricamento(NT.t('Testing the key…')));
      try { const r = await NT.api('POST', '/api/impostazioni/prova-owm'); NT.riempi(esitoProva, h('div', { class: 'banda ' + (r.ok ? 'verde' : 'rosso') }, NT.tr(r.messaggio))); }
      catch (e) { NT.riempi(esitoProva, h('div', { class: 'banda rosso' }, e.message)); }
    }
    disegnaOWM();

    /* ---------------- photo analysis ---------------- */
    const swSkin = h('input', { type: 'checkbox', id: 'sw-skin', checked: !!S.imp.usa_skinsense, onchange: async () => {
      if (swSkin.checked) {
        const ok = await NT.conferma(NT.t('Send the photos to SkinSense?'), NT.t('SkinSense is a third-party online service: the photos of your moles would be sent over the internet to a server we do not control. The photos are data about your health. Do you want to enable it?'), { si: NT.t('Yes, enable') });
        if (!ok) { swSkin.checked = false; return; }
      }
      if (!await salva({ usa_skinsense: swSkin.checked }, swSkin.checked ? NT.t('SkinSense turned on.') : NT.t('SkinSense turned off.'))) swSkin.checked = !swSkin.checked;
    } });
    const sezAnalisi = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Photo analysis')),
      h('label', { class: 'interruttore', for: 'sw-skin' }, swSkin, h('span', {}, h('strong', {}, NT.t('Also use SkinSense (online service)')),
        h('span', { class: 'piccolo muted blocco' }, NT.t('Off by default: with the other methods the photo never leaves this computer.')))),
      h('p', { class: 'piccolo muted' }, NT.t('Age, sex and phenotype do not change the output of the neural networks: they are used to show you the risk factors, choose the literature, evaluate the genetics criteria and estimate the time to sunburn.')));

    /* ---------------- PubMed ---------------- */
    const campoMail = h('input', { type: 'email', class: 'campo', value: S.imp.ncbi_email || '', placeholder: NT.t('name@example.com (optional)'), maxlength: 120, autocomplete: 'email', 'aria-label': NT.t('Email for PubMed') });
    const sezMail = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Literature: PubMed')),
      h('p', {}, NT.t("Searches use PubMed's public E-utilities. NCBI asks, as a courtesy, for a contact email: it is optional and is sent only to PubMed.")),
      h('div', { class: 'riga-inline' }, campoMail, h('button', { class: 'btn', onclick: () => salva({ ncbi_email: campoMail.value }, NT.t('Email saved.')) }, NT.t('Save'))));

    /* ---------------- status ---------------- */
    const st = S.stato;
    const sezStato = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Installation status')),
      h('ul', { class: 'stato-lista' }, st.progetti.map(p => h('li', { class: p.presente ? 'si' : 'no' },
        h('span', { class: 'esito-criterio' }, p.presente ? NT.icona('ok', 16) : NT.icona('avviso', 16)), h('div', {}, h('strong', {}, NT.tr(p.nome)), h('div', { class: 'piccolo muted' }, NT.tr(p.dettaglio)))))),
      h('div', { class: 'piccolo' }, st.batch ? [NT.t('Analysis program:') + ' ', h('code', {}, st.batch)] : h('span', { class: 'errore-campo' }, NT.t('Analysis program (melanoma_batch.py) not found: photos are saved but cannot be analysed.'))),
      h('div', { class: 'piccolo' }, NT.t('Projects folder:') + ' ', h('code', {}, st.repo)),
      h('div', { class: 'piccolo' }, NT.t('Folder with your data (copy it for backup):') + ' ', h('code', {}, st.cartella_dati)),
      st.pillow_obsoleto ? h('div', { class: 'errore-campo' }, NT.t('The Pillow library is old and has known security problems: update it with «py -m pip install -U pillow».')) : null,
      h('div', { class: 'piccolo muted' }, NT.t('Version') + ' ' + st.versione + (st.ha_pillow ? '' : ' · ' + NT.t('Pillow is not installed: previews will use the original photos (install with «py -m pip install pillow»).'))));

    /* ---------------- shutdown ---------------- */
    const sezEsci = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Closing the program')),
      h('p', {}, NT.t('To close NeoTracker, just close this window with the X at the top right: the program shuts down by itself.') + ' ' +
        NT.t('If it is still analysing a photo, it finishes the analysis first and then shuts down. The button below does the same thing.')),
      h('button', { class: 'btn btn-pericolo', onclick: async () => {
        if (!await NT.conferma(NT.t('Close NeoTracker?'), NT.t('The program will shut down. An analysis in progress will be interrupted. Your data stays saved.'), { si: NT.t('Close the program'), pericolo: true })) return;
        NT.battitoAttivo = false;
        if (NT.presenza) NT.presenza.close();       // it must not reconnect while the program is shutting down
        try { await NT.api('POST', '/api/chiudi'); } catch (e) { /* it is shutting down */ }
        NT.riempi(cont, h('div', { class: 'pagina stretta' }, h('div', { class: 'scheda' }, h('h2', {}, NT.t('NeoTracker is closed')), h('p', {}, NT.t('You can close this window. To reopen the program, use the «NeoTracker» icon on the Desktop.')))));
      } }, NT.icona('esci', 18), NT.t('Close NeoTracker')));

    NT.riempi(cont, h('div', { class: 'pagina' }, h('h1', {}, NT.t('Settings')), sezLingua, sezOWM, sezAnalisi, sezMail, sezStato, sezEsci));
  };
})();
