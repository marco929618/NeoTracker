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

    /* ---------------- indice UV: fonte dei dati ---------------- */
    const esitoProva = h('div', { class: 'prova-esito', role: 'status' });
    const campoChiave = h('input', { type: 'password', class: 'campo', autocomplete: 'off', spellcheck: 'false', maxlength: 64,
      placeholder: S.imp.ha_chiave_owm ? 'Chiave salvata (' + S.imp.chiave_owm_finale + ') — scrivine una nuova per sostituirla' : 'Incolla qui la chiave (32 lettere e numeri)', 'aria-label': 'Chiave OpenWeather' });
    const sezOWM = h('section', { class: 'scheda' });
    function disegnaOWM() {
      campoChiave.placeholder = S.imp.ha_chiave_owm ? 'Chiave salvata (' + S.imp.chiave_owm_finale + ') — scrivine una nuova per sostituirla' : 'Incolla qui la chiave (32 lettere e numeri)';
      const ow = S.imp.fonte_uv === 'openweather';
      // una riga con pallino: scegliere cambia subito la fonte e ridisegna la sezione
      const scelta = (valore, titolo, desc) => h('label', { class: 'riga-inline' },
        h('input', { type: 'radio', name: 'fonte-uv', value: valore, checked: S.imp.fonte_uv === valore,
          onchange: async () => { if (await salva({ fonte_uv: valore }, 'Fonte dell\'indice UV cambiata.')) { NT.riempi(esitoProva); disegnaOWM(); } } }),
        h('span', {}, h('strong', {}, titolo), ' ', h('span', { class: 'piccolo muted' }, desc)));
      NT.riempi(sezOWM, h('h2', {}, 'Indice UV: fonte dei dati'),
        scelta('open-meteo', 'Open-Meteo (predefinita)', 'gratuita, senza account né chiave'),
        scelta('openweather', 'OpenWeather', 'facoltativa: richiede una tua chiave personale'),
        !ow ? h('p', { class: 'piccolo muted' }, 'Dati meteo e UV: ', NT.link('https://open-meteo.com/', 'Open-Meteo.com'), ' (licenza CC BY 4.0). Il servizio gratuito è per uso personale e non commerciale. ',
          'Anche la ricerca delle città usa Open-Meteo.') : null,
        ow ? h('div', { class: 'banda ' + (S.imp.ha_chiave_owm ? 'verde' : 'giallo') }, S.imp.ha_chiave_owm ? 'Chiave OpenWeather salvata (' + S.imp.chiave_owm_finale + ').' : 'Hai scelto OpenWeather ma non c\'è ancora una chiave: finché manca, il programma usa Open-Meteo.') : null,
        ow ? h('div', { class: 'riga-inline' }, campoChiave,
          h('button', { class: 'btn btn-pri', onclick: async () => { const k = campoChiave.value.trim(); if (!k) { NT.toast('Incolla prima la chiave.', 'errore'); return; } if (await salva({ openweather_key: k }, 'Chiave salvata.')) { campoChiave.value = ''; NT.riempi(esitoProva); disegnaOWM(); } } }, 'Salva'),
          S.imp.ha_chiave_owm ? h('button', { class: 'btn', onclick: provaChiave }, 'Prova la chiave') : null,
          S.imp.ha_chiave_owm ? h('button', { class: 'btn-testo pericolo', onclick: async () => { if (await NT.conferma('Rimuovere la chiave?', 'La chiave sarà cancellata da questo computer. Potrai inserirla di nuovo quando vuoi.', { si: 'Rimuovi', pericolo: true }) && await salva({ openweather_key: '' }, 'Chiave rimossa.')) { NT.riempi(esitoProva); disegnaOWM(); } } }, 'Rimuovi') : null) : null,
        ow ? esitoProva : null,
        ow ? h('details', { class: 'abstract' }, h('summary', {}, 'Come ottenere la chiave'),
          h('ol', { class: 'passi' },
            h('li', {}, 'Crea un account gratuito su ', NT.link('https://home.openweathermap.org/users/sign_up', 'openweathermap.org'), ' e conferma l\'email.'),
            h('li', {}, 'Apri la pagina «API keys» del tuo account e copia la chiave.'),
            h('li', {}, 'Iscriviti all\'abbonamento «One Call API» a pagamento per chiamata (', NT.link('https://openweathermap.org/api/one-call-4', 'pagina del servizio'), '): le prime 1.000 chiamate al giorno sono gratuite, le successive si pagano. OpenWeather può chiedere una carta di pagamento per attivarlo: controlla le condizioni sul loro sito.'),
            h('li', {}, 'Alla sottoscrizione il limite giornaliero predefinito è di 2.000 chiamate: nella scheda «Billing plans» del tuo account puoi abbassarlo a 1.000, così non spendi nulla. NeoTracker ne usa poche (al massimo 4 ogni 10 minuti, solo quando apri la pagina Indice UV).'),
            h('li', {}, 'Incolla la chiave qui sopra e premi «Prova la chiave». Dopo l\'iscrizione la chiave può impiegare qualche minuto ad attivarsi. Il programma prova prima One Call 4.0 e, se la chiave è di un abbonamento più vecchio, One Call 3.0.')),
          h('p', { class: 'piccolo muted' }, 'La chiave resta salvata solo sul tuo computer e non viene mai mostrata né inviata alla pagina web del programma: la usa il programma Python per chiamare OpenWeather.')) : null);
    }
    async function provaChiave() {
      NT.riempi(esitoProva, NT.caricamento('Provo la chiave…'));
      try { const r = await NT.api('POST', '/api/impostazioni/prova-owm'); NT.riempi(esitoProva, h('div', { class: 'banda ' + (r.ok ? 'verde' : 'rosso') }, r.messaggio)); }
      catch (e) { NT.riempi(esitoProva, h('div', { class: 'banda rosso' }, e.message)); }
    }
    disegnaOWM();

    /* ---------------- analisi delle foto ---------------- */
    const swSkin = h('input', { type: 'checkbox', id: 'sw-skin', checked: !!S.imp.usa_skinsense, onchange: async () => {
      if (swSkin.checked) {
        const ok = await NT.conferma('Inviare le foto a SkinSense?', 'SkinSense è un servizio online di terzi: le foto dei tuoi nei verrebbero inviate via internet a un server che non controlliamo. Le foto sono dati sulla tua salute. Vuoi abilitarlo?', { si: 'Sì, abilita' });
        if (!ok) { swSkin.checked = false; return; }
      }
      if (!await salva({ usa_skinsense: swSkin.checked }, swSkin.checked ? 'SkinSense abilitato.' : 'SkinSense disattivato.')) swSkin.checked = !swSkin.checked;
    } });
    const sezAnalisi = h('section', { class: 'scheda' }, h('h2', {}, 'Analisi delle foto'),
      h('label', { class: 'interruttore', for: 'sw-skin' }, swSkin, h('span', {}, h('strong', {}, 'Usa anche SkinSense (servizio online)'),
        h('span', { class: 'piccolo muted blocco' }, 'Spento per impostazione predefinita: con gli altri metodi la foto non lascia mai questo computer.'))),
      h('p', { class: 'piccolo muted' }, 'Età, sesso e fenotipo non cambiano l\'uscita delle reti neurali: servono a mostrarti i fattori di rischio, a scegliere la letteratura, a valutare i criteri di genetica e a stimare il tempo di scottatura.'));

    /* ---------------- PubMed ---------------- */
    const campoMail = h('input', { type: 'email', class: 'campo', value: S.imp.ncbi_email || '', placeholder: 'nome@esempio.it (facoltativa)', maxlength: 120, autocomplete: 'email', 'aria-label': 'Email per PubMed' });
    const sezMail = h('section', { class: 'scheda' }, h('h2', {}, 'Letteratura: PubMed'),
      h('p', {}, 'Le ricerche usano le E-utilities pubbliche di PubMed. NCBI chiede, per cortesia, un\'email di contatto: è facoltativa e viene inviata solo a PubMed.'),
      h('div', { class: 'riga-inline' }, campoMail, h('button', { class: 'btn', onclick: () => salva({ ncbi_email: campoMail.value }, 'Email salvata.') }, 'Salva')));

    /* ---------------- stato ---------------- */
    const st = S.stato;
    const sezStato = h('section', { class: 'scheda' }, h('h2', {}, 'Stato dell\'installazione'),
      h('ul', { class: 'stato-lista' }, st.progetti.map(p => h('li', { class: p.presente ? 'si' : 'no' },
        h('span', { class: 'esito-criterio' }, p.presente ? NT.icona('ok', 16) : NT.icona('avviso', 16)), h('div', {}, h('strong', {}, p.nome), h('div', { class: 'piccolo muted' }, p.dettaglio))))),
      h('div', { class: 'piccolo' }, st.batch ? ['Programma di analisi: ', h('code', {}, st.batch)] : h('span', { class: 'errore-campo' }, 'Programma di analisi (melanoma_batch.py) non trovato: le foto si salvano ma non si possono analizzare.')),
      h('div', { class: 'piccolo' }, 'Cartella dei progetti: ', h('code', {}, st.repo)),
      h('div', { class: 'piccolo' }, 'Cartella dei tuoi dati (da copiare per il backup): ', h('code', {}, st.cartella_dati)),
      st.pillow_obsoleto ? h('div', { class: 'errore-campo' }, 'La libreria Pillow è vecchia e ha problemi di sicurezza noti: aggiornala con «py -m pip install -U pillow».') : null,
      h('div', { class: 'piccolo muted' }, 'Versione ' + st.versione + (st.ha_pillow ? '' : ' · Pillow non installato: le anteprime useranno le foto originali (installa con «py -m pip install pillow»).')));

    /* ---------------- chiusura ---------------- */
    const sezEsci = h('section', { class: 'scheda' }, h('h2', {}, 'Chiudere il programma'),
      h('p', {}, 'Per chiudere NeoTracker basta chiudere questa finestra con la X in alto a destra: il programma si spegne da solo. ' +
        'Se sta ancora analizzando una foto, finisce prima l\'analisi e poi si spegne. Il pulsante qui sotto fa la stessa cosa.'),
      h('button', { class: 'btn btn-pericolo', onclick: async () => {
        if (!await NT.conferma('Chiudere NeoTracker?', 'Il programma si spegne. Un\'analisi in corso viene interrotta. I dati restano salvati.', { si: 'Chiudi il programma', pericolo: true })) return;
        NT.battitoAttivo = false;
        if (NT.presenza) NT.presenza.close();       // non deve riconnettersi mentre il programma si spegne
        try { await NT.api('POST', '/api/chiudi'); } catch (e) { /* si sta spegnendo */ }
        NT.riempi(cont, h('div', { class: 'pagina stretta' }, h('div', { class: 'scheda' }, h('h2', {}, 'NeoTracker è chiuso'), h('p', {}, 'Puoi chiudere questa finestra. Per riaprirlo usa l\'icona «NeoTracker» sul Desktop.'))));
      } }, NT.icona('esci', 18), 'Chiudi NeoTracker'));

    NT.riempi(cont, h('div', { class: 'pagina' }, h('h1', {}, 'Impostazioni'), sezOWM, sezAnalisi, sezMail, sezStato, sezEsci));
  };
})();
