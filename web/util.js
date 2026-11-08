/* ============================================================================
   util.js - funzioni di servizio comuni a tutte le pagine
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT;                      // creato da i18n.js (che si carica per primo)
  Object.assign(NT, { S: { utenti: [], utente: null, nei: [], imp: {}, stato: {} }, viste: {}, pulizie: [] });

  NT.$ = (s, r) => (r || document).querySelector(s);
  NT.$$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  /* Crea elementi senza mai interpretare il testo come HTML (cosi' nomi e note degli utenti sono sicuri). */
  NT.h = function h(tag, attrs, ...figli) {
    const e = document.createElement(tag);
    for (const k in (attrs || {})) {
      const v = attrs[k];
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k === 'dataset') Object.assign(e.dataset, v);
      else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
      else if (k.slice(0, 2) === 'on' && typeof v === 'function') e.addEventListener(k.slice(2), v);
      else if (k === 'value' || k === 'checked' || k === 'selected' || k === 'disabled' || k === 'indeterminate') e[k] = v;
      else if (v === true) e.setAttribute(k, '');
      else e.setAttribute(k, v);
    }
    (function aggiungi(lista) {
      for (const f of lista) {
        if (f === null || f === undefined || f === false) continue;
        if (Array.isArray(f)) aggiungi(f);
        else if (f instanceof Node) e.appendChild(f);
        else e.appendChild(document.createTextNode(String(f)));
      }
    })(figli);
    return e;
  };
  const h = NT.h;

  /* Svuota un elemento e lo riempie con elementi, testi, liste (anche annidate); ignora null e false. */
  NT.riempi = function (el, ...figli) {
    const frag = document.createDocumentFragment();
    (function aggiungi(lista) {
      for (const f of lista) {
        if (f === null || f === undefined || f === false) continue;
        if (Array.isArray(f)) aggiungi(f);
        else frag.appendChild(f instanceof Node ? f : document.createTextNode(String(f)));
      }
    })(figli);
    el.replaceChildren(frag);
    return el;
  };

  /* HTML fidato (solo SVG/icone scritti da noi, con numeri e testi gia' "escapati") */
  NT.html = function (stringa) {
    const t = document.createElement('template');
    t.innerHTML = stringa.trim();
    return t.content.firstChild;
  };
  NT.esc = t => String(t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const ICONE = {
    mappa: '<circle cx="12" cy="5" r="2.5"/><path d="M12 8.5v6.5M6.5 10.5 12 8.5l5.5 2M9.5 21.5 12 15l2.5 6.5"/>',
    profilo: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
    letteratura: '<path d="M12 6c-2-1.5-5-2-8-2v14c3 0 6 .5 8 2 2-1.5 5-2 8-2V4c-3 0-6 .5-8 2zM12 6v14"/>',
    genetica: '<path d="M6 3c0 5 12 5 12 9s-12 4-12 9"/><path d="M18 3c0 5-12 5-12 9s12 4 12 9"/><path d="M8.6 6.6h6.8M8.6 17.4h6.8"/>',
    uv: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2.2M12 19.8V22M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M2 12h2.2M19.8 12H22M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6"/>',
    impostazioni: '<path d="M4 6h9M19 6h1M4 12h3M13 12h7M4 18h11M21 18h-1"/><circle cx="16" cy="6" r="2.2"/><circle cx="10" cy="12" r="2.2"/><circle cx="18" cy="18" r="2.2"/>',
    piu: '<path d="M12 5v14M5 12h14"/>', meno: '<path d="M5 12h14"/>',
    reset: '<path d="M4 12a8 8 0 1 0 2.6-5.9M4 4v4.5h4.5"/>',
    stampa: '<path d="M7 9V3h10v6M7 17H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2"/><path d="M7 14h10v7H7z"/>',
    foto: '<path d="M4 8h3l1.6-2.5h6.8L17 8h3v11H4z"/><circle cx="12" cy="13" r="3.6"/>',
    cestino: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    mirino: '<circle cx="12" cy="12" r="7"/><path d="M12 2v5M12 17v5M2 12h5M17 12h5"/>',
    archivio: '<path d="M3 5h18v4H3zM5 9v10h14V9M10 13h4"/>',
    freccia: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    esci: '<path d="M9 4H5v16h4M16 8l4 4-4 4M20 12H9"/>',
    avviso: '<path d="M12 3 2 20h20zM12 10v5M12 17.6v.2"/>',
    ok: '<path d="M5 12.5 10 17.5 19 7"/>',
    posizione: '<path d="M12 21s-7-6.2-7-11.3A7 7 0 0 1 19 9.7C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.7" r="2.4"/>',
    cerca: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    esterno: '<path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6"/>',
    confronta: '<rect x="3" y="5" width="8" height="14" rx="1.5"/><rect x="13" y="5" width="8" height="14" rx="1.5"/>',
  };
  NT.icona = (nome, dim) => NT.html('<svg class="ico" viewBox="0 0 24 24" width="' + (dim || 18) + '" height="' + (dim || 18) +
    '" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (ICONE[nome] || '') + '</svg>');

  /* ---------- chiamate al programma (API) ---------- */
  NT.api = async function (metodo, url, corpo, opz) {
    opz = opz || {};
    const init = { method: metodo, headers: { 'X-NeoTracker': '1' } };
    if (opz.raw) { init.body = opz.raw; init.headers['Content-Type'] = opz.tipo || 'application/octet-stream'; }
    else if (corpo !== undefined && corpo !== null) { init.body = JSON.stringify(corpo); init.headers['Content-Type'] = 'application/json'; }
    let r;
    try { r = await fetch(url, init); }
    catch (e) { throw new Error(NT.t('Non riesco a contattare NeoTracker. Il programma potrebbe essere stato chiuso: riaprilo dall\'icona sul Desktop.')); }
    const t = await r.text();
    let d = null;
    try { d = t ? JSON.parse(t) : null; } catch (e) { /* risposta non JSON */ }
    if (!r.ok) { const er = new Error((d && d.errore) ? NT.tr(d.errore) : NT.t('Errore {codice}', { codice: r.status })); er.codice = r.status; throw er; }
    return d;
  };
  NT.get = (url) => NT.api('GET', url);

  /* ---------- messaggi a comparsa ---------- */
  let timerToast = null;
  NT.toast = function (testo, tipo) {
    const t = NT.$('#toast');
    t.className = 'visibile ' + (tipo || 'info');
    t.textContent = testo;
    clearTimeout(timerToast);
    timerToast = setTimeout(() => { t.className = ''; }, tipo === 'errore' ? 7000 : 3500);
  };
  NT.errore = (e) => { console.error(e); NT.toast(e && e.message ? e.message : String(e), 'errore'); };

  /* ---------- finestre di dialogo ---------- */
  NT.apriDialogo = function (contenuto, larga) {
    const d = NT.$('#dialogo');
    d.className = larga ? 'larga' : '';
    d.replaceChildren(h('div', { class: 'dlg' }, contenuto));
    if (!d.open) d.showModal();
    return d;
  };
  NT.chiudiDialogo = () => { const d = NT.$('#dialogo'); if (d.open) d.close(); };

  NT.conferma = function (titolo, testo, opz) {
    opz = opz || {};
    return new Promise(res => {
      let fatto = false;
      const fine = v => { if (!fatto) { fatto = true; res(v); } NT.chiudiDialogo(); };
      const campo = opz.scrivi ? h('input', { type: 'text', class: 'campo', autocomplete: 'off', placeholder: opz.scrivi,
        oninput: () => { ok.disabled = campo.value.trim() !== opz.scrivi; } }) : null;
      const ok = h('button', { class: 'btn ' + (opz.pericolo ? 'btn-pericolo' : 'btn-pri'), disabled: !!opz.scrivi, onclick: () => fine(campo ? campo.value.trim() : true) }, opz.si || NT.t('Conferma'));
      const d = NT.apriDialogo(h('div', {},
        h('h3', {}, titolo), h('p', {}, testo),
        opz.scrivi ? h('label', { class: 'etichetta' }, NT.t('Per confermare scrivi:') + ' ', h('strong', {}, opz.scrivi)) : null, campo,
        h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => fine(false) }, NT.t('Annulla')), ok)));
      d.addEventListener('close', () => fine(false), { once: true });
      if (campo) campo.focus();
    });
  };

  document.addEventListener('click', ev => {                  // clic fuori dalla finestra = chiude
    const d = ev.target;
    if (d instanceof HTMLDialogElement && d.open) {
      const r = d.getBoundingClientRect();
      if (ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom) d.close();
    }
  });

  /* ---------- date e varie ---------- */
  NT.oggiISO = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  NT.dataDaMs = ms => { const d = new Date(ms); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  NT.giorniTra = (a, b) => Math.round((new Date(b + 'T12:00:00') - new Date(a + 'T12:00:00')) / 86400000);
  NT.ls = {
    leggi: k => { try { return localStorage.getItem(k); } catch (e) { return null; } },
    scrivi: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* non disponibile */ } },
  };
  NT.debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

  /* spinner e segnaposto */
  NT.caricamento = (testo) => h('div', { class: 'caricamento' }, h('span', { class: 'spinner' }), testo || NT.t('Caricamento…'));
  NT.vuoto = (titolo, testo) => h('div', { class: 'vuoto' }, h('strong', {}, titolo), testo ? h('p', {}, testo) : null);

  /* Etichetta dell'esito dell'analisi (colori volutamente prudenti: "benigno" non e' mai verde rassicurante) */
  NT.ESITI = {
    attenzione: { testo: NT.t('Da attenzionare'), cls: 'esito-att' },
    discordante: { testo: NT.t('Metodi in disaccordo'), cls: 'esito-disc' },
    benigno: { testo: NT.t('Nessun allarme dai modelli'), cls: 'esito-ben' },
    nessuno: { testo: NT.t('Nessun risultato'), cls: 'esito-nes' },
  };
  NT.chipEsito = (esito) => { const e = NT.ESITI[esito]; return e ? h('span', { class: 'chip ' + e.cls }, e.testo) : null; };

  NT.link = (url, testo) => h('a', { href: url, target: '_blank', rel: 'noopener noreferrer', class: 'link-est' }, testo, NT.icona('esterno', 13));

  /* Prende un file immagine e restituisce (come Blob JPEG) un quadrato "lato x lato" ritagliato al centro.
     Il JPEG nuovo non contiene i metadati dell'originale (posizione GPS, modello di fotocamera...). */
  NT.ridimensionaQuadrato = function (file, lato) {
    return new Promise((res, rej) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        try {
          const w = img.naturalWidth, alt = img.naturalHeight;
          if (!w || !alt) throw new Error('vuota');
          const q = Math.min(w, alt), sx = (w - q) / 2, sy = (alt - q) / 2;
          const c = document.createElement('canvas');
          c.width = c.height = lato;
          const g = c.getContext('2d');
          g.fillStyle = '#ffffff'; g.fillRect(0, 0, lato, lato);          // le parti trasparenti diventano bianche
          g.imageSmoothingQuality = 'high';
          g.drawImage(img, sx, sy, q, q, 0, 0, lato, lato);
          c.toBlob(b => b ? res(b) : rej(new Error(NT.t('Non riesco a ridurre questa immagine.'))), 'image/jpeg', 0.88);
        } catch (e) { rej(new Error(NT.t('Non riesco a leggere questa immagine. Prova con un JPG o un PNG.'))); }
        finally { URL.revokeObjectURL(url); }
      };
      img.onerror = () => { URL.revokeObjectURL(url); rej(new Error(NT.t('Non riesco a leggere questa immagine. Prova con un JPG o un PNG.'))); };
      img.src = url;
    });
  };

  /* Avviso iniziale (primo avvio): NeoTracker non e' un dispositivo medico. Va accettato per continuare. */
  NT.mostraAvvertenze = function () {
    const spunta = h('input', { type: 'checkbox', id: 'ck-avvertenze' });
    const ok = h('button', { class: 'btn btn-pri', disabled: true, onclick: async () => {
      try {
        NT.S.imp = await NT.api('PUT', '/api/impostazioni', { avvertenze_accettate: NT.S.stato.avvertenze_versione });
        NT.chiudiDialogo();
      } catch (e) { NT.errore(e); }
    } }, NT.t('Accetto e continuo'));
    spunta.addEventListener('change', () => { ok.disabled = !spunta.checked; });
    const d = NT.apriDialogo(h('div', { class: 'avvertenze' },
      h('h3', {}, NT.t('Prima di cominciare')),
      h('p', {}, h('strong', {}, NT.t('NeoTracker non è un dispositivo medico e non fa diagnosi.') + ' '),
        NT.t('È uno strumento personale per organizzare le foto dei tuoi nei e confrontare nel tempo i risultati di alcuni modelli di ricerca. Non è certificato né approvato da alcuna autorità sanitaria.')),
      h('ul', {},
        h('li', {}, NT.t('I risultati sono stime sperimentali e possono sbagliare in entrambe le direzioni: un esito rassicurante non esclude un melanoma, un esito di attenzione non significa che ci sia.')),
        h('li', {}, NT.t('Un neo che cambia (forma, bordi, colore, dimensioni), sanguina, prude o ti preoccupa va mostrato a un dermatologo, qualunque cosa dica l\'app. Il controllo periodico dal dermatologo resta insostituibile.')),
        h('li', {}, NT.t('Le informazioni su rischio, letteratura e genetica sono divulgative e non sostituiscono la consulenza di un medico o di un genetista.')),
        h('li', {}, NT.t('I dati (anche di salute) restano su questo computer. Escono solo le richieste che attivi tu: indice UV (coordinate approssimate), ricerche su PubMed (solo i termini cercati) e, solo se lo attivi, l\'invio della foto a SkinSense.')),
        h('li', {}, NT.t('Se inserisci dati o foto di altre persone, assicurati di avere il loro consenso.'))),
      h('label', { class: 'spunta grande' }, spunta, ' ' + NT.t('Ho letto e capito queste avvertenze')),
      h('div', { class: 'azioni' },
        h('button', { class: 'btn', onclick: () => { NT.api('POST', '/api/chiudi').catch(() => {}); NT.battitoAttivo = false; if (NT.presenza) NT.presenza.close(); document.title = NT.t('NeoTracker chiuso'); NT.chiudiDialogo(); } }, NT.t('Esci dal programma')),
        ok)));
    d.addEventListener('cancel', ev => ev.preventDefault());           // il tasto Esc non salta l'avviso
    return d;
  };

  /* pulizie da eseguire quando si cambia pagina (timer, osservatori...) */
  NT.alCambioPagina = fn => NT.pulizie.push(fn);
})();
