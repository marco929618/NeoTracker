/* ============================================================================
   app.js - avvio, menu, scelta pagina e utente corrente
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h, $ = NT.$;

  const VOCI = [
    ['mappa', 'Mappa dei nei', 'mappa'], ['profilo', 'Profilo', 'profilo'], ['letteratura', 'Letteratura', 'letteratura'],
    ['genetica', 'Genetica', 'genetica'], ['uv', 'Indice UV', 'uv'], ['impostazioni', 'Impostazioni', 'impostazioni'],
  ];

  NT.colorePerNome = nome => { let x = 0; for (const c of nome) x = (x * 31 + c.charCodeAt(0)) % 360; return 'hsl(' + x + ',45%,38%)'; };
  /* Cerchio con l'immagine personale dell'utente (se l'ha scelta) oppure con l'iniziale del nome.
     "utente" e' facoltativo: serve solo ad avere id e versione dell'immagine (avatar_v, 0 = nessuna). */
  NT.avatar = (nome, dim, utente) => {
    const d = dim || 32, iniziale = (nome.trim()[0] || '?').toUpperCase();
    const cerchio = h('span', { class: 'avatar', style: { background: NT.colorePerNome(nome), width: d + 'px', height: d + 'px', fontSize: Math.round(d * 0.45) + 'px' } }, iniziale);
    if (utente && utente.avatar_v) {
      const img = h('img', { class: 'avatar-img', alt: '', draggable: 'false', src: '/api/utenti/' + utente.id + '/avatar?v=' + utente.avatar_v });
      img.addEventListener('error', () => cerchio.replaceChildren(iniziale));         // se l'immagine manca, torna l'iniziale
      cerchio.replaceChildren(img);
    }
    return cerchio;
  };

  NT.vai = nome => { if (location.hash === '#/' + nome) route(); else location.hash = '#/' + nome; };
  const nomeRotta = () => { const m = /^#\/(\w+)/.exec(location.hash); return m ? m[1] : 'mappa'; };

  function disegnaTestata(attiva) {
    const menu = $('#menu');
    menu.replaceChildren(...VOCI.map(([id, testo, ico]) =>
      h('a', { href: '#/' + id, class: 'voce' + (id === attiva ? ' attiva' : ''), 'aria-current': id === attiva ? 'page' : null }, NT.icona(ico, 18), h('span', {}, testo))));
    const box = $('#utente-box');
    box.replaceChildren(S.utente
      ? h('a', { href: '#/utenti', class: 'utente-chip', title: 'Cambia utente' }, NT.avatar(S.utente.nome, 28, S.utente),
        h('span', { class: 'utente-nome' }, S.utente.nome), h('span', { class: 'utente-cambia' }, 'Cambia'))
      : h('a', { href: '#/utenti', class: 'utente-chip' }, h('span', { class: 'utente-nome' }, 'Scegli utente')));
  }

  async function route() {
    NT.pulizie.splice(0).forEach(f => { try { f(); } catch (e) { /* ignora */ } });
    let nome = nomeRotta();
    const serveUtente = ['mappa', 'profilo', 'genetica'];
    if (!S.utente && serveUtente.includes(nome)) nome = 'utenti';
    if (!NT.viste[nome]) nome = S.utente ? 'mappa' : 'utenti';
    disegnaTestata(nome === 'utenti' ? '' : nome);
    const cont = $('#vista');
    cont.className = 'vista-' + nome;
    cont.replaceChildren(NT.caricamento());
    try { await NT.viste[nome](cont); }
    catch (e) {
      console.error(e);
      cont.replaceChildren(h('div', { class: 'scheda errore-pagina' }, h('h2', {}, 'Qualcosa non ha funzionato'), h('p', {}, e.message || String(e)),
        h('button', { class: 'btn', onclick: () => route() }, 'Riprova')));
    }
    window.scrollTo(0, 0);
  }
  NT.ridisegnaTestata = () => disegnaTestata(nomeRotta());

  NT.scegliUtente = async function (id, vai) {
    S.utente = await NT.get('/api/utenti/' + id);
    S.nei = await NT.get('/api/utenti/' + id + '/nevi');
    NT.ls.scrivi('nt_utente', String(id));
    NT.ridisegnaTestata();
    if (vai !== false) NT.vai('mappa');
  };
  NT.ricaricaUtente = async function () {
    if (!S.utente) return;
    S.utente = await NT.get('/api/utenti/' + S.utente.id);
    NT.ridisegnaTestata();
  };
  NT.ricaricaNei = async function () {
    if (!S.utente) return [];
    S.nei = await NT.get('/api/utenti/' + S.utente.id + '/nevi');
    return S.nei;
  };

  /* ---- "battito": ogni pochi secondi la pagina dice al programma "sono ancora aperta" ----
     Quando la finestra viene chiusa i battiti finiscono (e parte un ultimo messaggio di "addio"):
     il programma capisce che può spegnersi. Ogni pagina ha un numero casuale, così più finestre
     aperte insieme non si confondono. */
  const nuovoId = () => (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
    : String(Date.now()) + Math.random().toString(36).slice(2);
  let ID_PAGINA = nuovoId();
  NT.battitoAttivo = true;                       // diventa false dopo "Chiudi NeoTracker" (non deve più battere)
  function segnale(percorso) {
    if (!NT.battitoAttivo && percorso === '/api/battito') return;
    try {
      // keepalive: la richiesta parte anche mentre la pagina si sta chiudendo
      fetch(percorso, { method: 'POST', keepalive: true,
        headers: { 'Content-Type': 'application/json', 'X-NeoTracker': '1' },
        body: JSON.stringify({ id: ID_PAGINA }) }).catch(() => { /* programma già spento: va bene */ });
    } catch (e) { /* ignora */ }
  }
  // Connessione di presenza: resta aperta finché la pagina è aperta. Quando la finestra si chiude
  // (in qualunque modo) il programma lo nota subito. Si riconnette da sola se cade.
  function apriPresenza() {
    if (NT.presenza) { try { NT.presenza.close(); } catch (e) { /* ignora */ } }
    try { NT.presenza = new EventSource('/api/presenza?id=' + encodeURIComponent(ID_PAGINA)); } catch (e) { NT.presenza = null; }
  }
  apriPresenza();
  segnale('/api/battito');
  setInterval(() => segnale('/api/battito'), 5000);
  window.addEventListener('pageshow', ev => {
    // Se il browser ci "risveglia" da una copia messa da parte (ev.persisted), il programma aveva già
    // ricevuto l'addio: ci presentiamo come una pagina nuova, con un numero nuovo.
    if (ev.persisted) { ID_PAGINA = nuovoId(); apriPresenza(); }
    segnale('/api/battito');
  });
  window.addEventListener('pagehide', () => segnale('/api/addio'));
  document.addEventListener('visibilitychange', () => { if (!document.hidden) segnale('/api/battito'); });

  async function avvia() {
    try {
      [S.stato, S.imp, S.utenti] = await Promise.all([NT.get('/api/stato'), NT.get('/api/impostazioni'), NT.get('/api/utenti')]);
      const ultimo = parseInt(NT.ls.leggi('nt_utente') || '', 10);
      if (ultimo && S.utenti.some(u => u.id === ultimo)) await NT.scegliUtente(ultimo, false);
    } catch (e) {
      $('#vista').replaceChildren(h('div', { class: 'scheda errore-pagina' }, h('h2', {}, 'NeoTracker non risponde'), h('p', {}, e.message)));
      return;
    }
    window.addEventListener('hashchange', route);
    if (!location.hash || location.hash === '#') location.hash = S.utente ? '#/mappa' : '#/utenti';
    else route();
    if (S.imp.avvertenze_accettate !== S.stato.avvertenze_versione) NT.mostraAvvertenze();     // primo avvio (o avviso aggiornato)
  }
  avvia();
})();
