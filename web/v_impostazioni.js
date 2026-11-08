/* ============================================================================
   v_impostazioni.js - fonte dell'indice UV (Open-Meteo / OpenWeather), SkinSense, email PubMed, stato dell'installazione
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

    /* ---------------- lingua dell'interfaccia ---------------- */
    // 'auto' = la lingua del sistema; per applicare la scelta si salva e si ricarica la pagina
    const selLingua = h('select', { class: 'campo', id: 'sel-lingua', 'aria-label': NT.t('Lingua dell\'interfaccia'),
      onchange: async () => { if (await salva({ lingua: selLingua.value })) location.reload(); else selLingua.value = NT.linguaScelta; } },
      h('option', { value: 'auto' }, NT.t('Automatica (come il sistema)')),
      NT.LINGUE.map(l => h('option', { value: l[0] }, l[1])));
    selLingua.value = NT.linguaScelta;
    const sezLingua = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Lingua')),
      h('label', { for: 'sel-lingua', class: 'blocco' }, NT.t('Lingua dell\'interfaccia')), selLingua,
      h('p', { class: 'piccolo muted' }, NT.t('La scelta vale per tutti gli utenti di questo computer. Il testo originale e vincolante delle avvertenze legali è quello italiano; il rapporto di testo completo resta in italiano.')));

    /* ---------------- indice UV: fonte dei dati ---------------- */
    const esitoProva = h('div', { class: 'prova-esito', role: 'status' });
    const campoChiave = h('input', { type: 'password', class: 'campo', autocomplete: 'off', spellcheck: 'false', maxlength: 64,
      placeholder: '', 'aria-label': NT.t('Chiave OpenWeather') });
    const segnapostoChiave = () => S.imp.ha_chiave_owm ? NT.t('Chiave salvata ({finale}) — scrivine una nuova per sostituirla', { finale: S.imp.chiave_owm_finale }) : NT.t('Incolla qui la chiave (32 lettere e numeri)');
    campoChiave.placeholder = segnapostoChiave();
    const sezOWM = h('section', { class: 'scheda' });
    function disegnaOWM() {
      campoChiave.placeholder = segnapostoChiave();
      const ow = S.imp.fonte_uv === 'openweather';
      // una riga con pallino: scegliere cambia subito la fonte e ridisegna la sezione
      const scelta = (valore, titolo, desc) => h('label', { class: 'riga-inline' },
        h('input', { type: 'radio', name: 'fonte-uv', value: valore, checked: S.imp.fonte_uv === valore,
          onchange: async () => { if (await salva({ fonte_uv: valore }, NT.t('Fonte dell\'indice UV cambiata.'))) { NT.riempi(esitoProva); disegnaOWM(); } } }),
        h('span', {}, h('strong', {}, titolo), ' ', h('span', { class: 'piccolo muted' }, desc)));
      NT.riempi(sezOWM, h('h2', {}, NT.t('Indice UV: fonte dei dati')),
        scelta('open-meteo', NT.t('Open-Meteo (predefinita)'), NT.t('gratuita, senza account né chiave')),
        scelta('openweather', 'OpenWeather', NT.t('facoltativa: richiede una tua chiave personale')),
        !ow ? h('p', { class: 'piccolo muted' }, NT.t('Dati meteo e UV:') + ' ', NT.link('https://open-meteo.com/', 'Open-Meteo.com'), ' ' + NT.t('(licenza CC BY 4.0). Il servizio gratuito è per uso personale e non commerciale.') + ' ',
          NT.t('Anche la ricerca delle città usa Open-Meteo.')) : null,
        ow ? h('div', { class: 'banda ' + (S.imp.ha_chiave_owm ? 'verde' : 'giallo') }, S.imp.ha_chiave_owm ? NT.t('Chiave OpenWeather salvata ({finale}).', { finale: S.imp.chiave_owm_finale }) : NT.t('Hai scelto OpenWeather ma non c\'è ancora una chiave: finché manca, il programma usa Open-Meteo.')) : null,
        ow ? h('div', { class: 'riga-inline' }, campoChiave,
          h('button', { class: 'btn btn-pri', onclick: async () => { const k = campoChiave.value.trim(); if (!k) { NT.toast(NT.t('Incolla prima la chiave.'), 'errore'); return; } if (await salva({ openweather_key: k }, NT.t('Chiave salvata.'))) { campoChiave.value = ''; NT.riempi(esitoProva); disegnaOWM(); } } }, NT.t('Salva')),
          S.imp.ha_chiave_owm ? h('button', { class: 'btn', onclick: provaChiave }, NT.t('Prova la chiave')) : null,
          S.imp.ha_chiave_owm ? h('button', { class: 'btn-testo pericolo', onclick: async () => { if (await NT.conferma(NT.t('Rimuovere la chiave?'), NT.t('La chiave sarà cancellata da questo computer. Potrai inserirla di nuovo quando vuoi.'), { si: NT.t('Rimuovi'), pericolo: true }) && await salva({ openweather_key: '' }, NT.t('Chiave rimossa.'))) { NT.riempi(esitoProva); disegnaOWM(); } } }, NT.t('Rimuovi')) : null) : null,
        ow ? esitoProva : null,
        ow ? h('details', { class: 'abstract' }, h('summary', {}, NT.t('Come ottenere la chiave')),
          h('ol', { class: 'passi' },
            h('li', {}, NT.t('Crea un account gratuito su') + ' ', NT.link('https://home.openweathermap.org/users/sign_up', 'openweathermap.org'), ' ' + NT.t('e conferma l\'email.')),
            h('li', {}, NT.t('Apri la pagina «API keys» del tuo account e copia la chiave.')),
            h('li', {}, NT.t('Iscriviti all\'abbonamento «One Call API» a pagamento per chiamata') + ' (', NT.link('https://openweathermap.org/api/one-call-4', NT.t('pagina del servizio')), '): ' + NT.t('le prime 1.000 chiamate al giorno sono gratuite, le successive si pagano. OpenWeather può chiedere una carta di pagamento per attivarlo: controlla le condizioni sul loro sito.')),
            h('li', {}, NT.t('Alla sottoscrizione il limite giornaliero predefinito è di 2.000 chiamate: nella scheda «Billing plans» del tuo account puoi abbassarlo a 1.000, così non spendi nulla. NeoTracker ne usa poche (al massimo 4 ogni 10 minuti, solo quando apri la pagina Indice UV).')),
            h('li', {}, NT.t('Incolla la chiave qui sopra e premi «Prova la chiave». Dopo l\'iscrizione la chiave può impiegare qualche minuto ad attivarsi. Il programma prova prima One Call 4.0 e, se la chiave è di un abbonamento più vecchio, One Call 3.0.'))),
          h('p', { class: 'piccolo muted' }, NT.t('La chiave resta salvata solo sul tuo computer e non viene mai mostrata né inviata alla pagina web del programma: la usa il programma Python per chiamare OpenWeather.'))) : null);
    }
    async function provaChiave() {
      NT.riempi(esitoProva, NT.caricamento(NT.t('Provo la chiave…')));
      try { const r = await NT.api('POST', '/api/impostazioni/prova-owm'); NT.riempi(esitoProva, h('div', { class: 'banda ' + (r.ok ? 'verde' : 'rosso') }, NT.tr(r.messaggio))); }
      catch (e) { NT.riempi(esitoProva, h('div', { class: 'banda rosso' }, e.message)); }
    }
    disegnaOWM();

    /* ---------------- analisi delle foto ---------------- */
    const swSkin = h('input', { type: 'checkbox', id: 'sw-skin', checked: !!S.imp.usa_skinsense, onchange: async () => {
      if (swSkin.checked) {
        const ok = await NT.conferma(NT.t('Inviare le foto a SkinSense?'), NT.t('SkinSense è un servizio online di terzi: le foto dei tuoi nei verrebbero inviate via internet a un server che non controlliamo. Le foto sono dati sulla tua salute. Vuoi abilitarlo?'), { si: NT.t('Sì, abilita') });
        if (!ok) { swSkin.checked = false; return; }
      }
      if (!await salva({ usa_skinsense: swSkin.checked }, swSkin.checked ? NT.t('SkinSense abilitato.') : NT.t('SkinSense disattivato.'))) swSkin.checked = !swSkin.checked;
    } });
    const sezAnalisi = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Analisi delle foto')),
      h('label', { class: 'interruttore', for: 'sw-skin' }, swSkin, h('span', {}, h('strong', {}, NT.t('Usa anche SkinSense (servizio online)')),
        h('span', { class: 'piccolo muted blocco' }, NT.t('Spento per impostazione predefinita: con gli altri metodi la foto non lascia mai questo computer.')))),
      h('p', { class: 'piccolo muted' }, NT.t('Età, sesso e fenotipo non cambiano l\'uscita delle reti neurali: servono a mostrarti i fattori di rischio, a scegliere la letteratura, a valutare i criteri di genetica e a stimare il tempo di scottatura.')));

    /* ---------------- PubMed ---------------- */
    const campoMail = h('input', { type: 'email', class: 'campo', value: S.imp.ncbi_email || '', placeholder: NT.t('nome@esempio.it (facoltativa)'), maxlength: 120, autocomplete: 'email', 'aria-label': NT.t('Email per PubMed') });
    const sezMail = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Letteratura: PubMed')),
      h('p', {}, NT.t('Le ricerche usano le E-utilities pubbliche di PubMed. NCBI chiede, per cortesia, un\'email di contatto: è facoltativa e viene inviata solo a PubMed.')),
      h('div', { class: 'riga-inline' }, campoMail, h('button', { class: 'btn', onclick: () => salva({ ncbi_email: campoMail.value }, NT.t('Email salvata.')) }, NT.t('Salva'))));

    /* ---------------- stato ---------------- */
    const st = S.stato;
    const sezStato = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Stato dell\'installazione')),
      h('ul', { class: 'stato-lista' }, st.progetti.map(p => h('li', { class: p.presente ? 'si' : 'no' },
        h('span', { class: 'esito-criterio' }, p.presente ? NT.icona('ok', 16) : NT.icona('avviso', 16)), h('div', {}, h('strong', {}, NT.tr(p.nome)), h('div', { class: 'piccolo muted' }, NT.tr(p.dettaglio)))))),
      h('div', { class: 'piccolo' }, st.batch ? [NT.t('Programma di analisi:') + ' ', h('code', {}, st.batch)] : h('span', { class: 'errore-campo' }, NT.t('Programma di analisi (melanoma_batch.py) non trovato: le foto si salvano ma non si possono analizzare.'))),
      h('div', { class: 'piccolo' }, NT.t('Cartella dei progetti:') + ' ', h('code', {}, st.repo)),
      h('div', { class: 'piccolo' }, NT.t('Cartella dei tuoi dati (da copiare per il backup):') + ' ', h('code', {}, st.cartella_dati)),
      st.pillow_obsoleto ? h('div', { class: 'errore-campo' }, NT.t('La libreria Pillow è vecchia e ha problemi di sicurezza noti: aggiornala con «py -m pip install -U pillow».')) : null,
      h('div', { class: 'piccolo muted' }, NT.t('Versione') + ' ' + st.versione + (st.ha_pillow ? '' : ' · ' + NT.t('Pillow non installato: le anteprime useranno le foto originali (installa con «py -m pip install pillow»).'))));

    /* ---------------- chiusura ---------------- */
    const sezEsci = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Chiudere il programma')),
      h('p', {}, NT.t('Per chiudere NeoTracker basta chiudere questa finestra con la X in alto a destra: il programma si spegne da solo.') + ' ' +
        NT.t('Se sta ancora analizzando una foto, finisce prima l\'analisi e poi si spegne. Il pulsante qui sotto fa la stessa cosa.')),
      h('button', { class: 'btn btn-pericolo', onclick: async () => {
        if (!await NT.conferma(NT.t('Chiudere NeoTracker?'), NT.t('Il programma si spegne. Un\'analisi in corso viene interrotta. I dati restano salvati.'), { si: NT.t('Chiudi il programma'), pericolo: true })) return;
        NT.battitoAttivo = false;
        if (NT.presenza) NT.presenza.close();       // non deve riconnettersi mentre il programma si spegne
        try { await NT.api('POST', '/api/chiudi'); } catch (e) { /* si sta spegnendo */ }
        NT.riempi(cont, h('div', { class: 'pagina stretta' }, h('div', { class: 'scheda' }, h('h2', {}, NT.t('NeoTracker è chiuso')), h('p', {}, NT.t('Puoi chiudere questa finestra. Per riaprirlo usa l\'icona «NeoTracker» sul Desktop.')))));
      } }, NT.icona('esci', 18), NT.t('Chiudi NeoTracker')));

    NT.riempi(cont, h('div', { class: 'pagina' }, h('h1', {}, NT.t('Impostazioni')), sezLingua, sezOWM, sezAnalisi, sezMail, sezStato, sezEsci));
  };
})();
