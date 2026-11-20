/* ============================================================================
   app.js - start-up, menu, page choice and current user
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h, $ = NT.$;

  const VOCI = [
    ['mappa', NT.t('Mole map'), 'mappa'], ['profilo', NT.t('Profile'), 'profilo'], ['letteratura', NT.t('Literature'), 'letteratura'],
    ['genetica', NT.t('Genetics'), 'genetica'], ['uv', NT.t('UV index'), 'uv'], ['impostazioni', NT.t('Settings'), 'impostazioni'],
  ];

  NT.colorePerNome = nome => { let x = 0; for (const c of nome) x = (x * 31 + c.charCodeAt(0)) % 360; return 'hsl(' + x + ',45%,38%)'; };
  /* Circle with the user's personal image (if they chose one) or with the initial of their name.
     "utente" is optional: it only serves to have the id and version of the image (avatar_v, 0 = none). */
  NT.avatar = (nome, dim, utente) => {
    const d = dim || 32, iniziale = (nome.trim()[0] || '?').toUpperCase();
    const cerchio = h('span', { class: 'avatar', style: { background: NT.colorePerNome(nome), width: d + 'px', height: d + 'px', fontSize: Math.round(d * 0.45) + 'px' } }, iniziale);
    if (utente && utente.avatar_v) {
      const img = h('img', { class: 'avatar-img', alt: '', draggable: 'false', src: '/api/utenti/' + utente.id + '/avatar?v=' + utente.avatar_v });
      img.addEventListener('error', () => cerchio.replaceChildren(iniziale));         // if the image is missing, it falls back to the initial
      cerchio.replaceChildren(img);
    }
    return cerchio;
  };

  NT.vai = nome => { if (location.hash === '#/' + nome) route(); else location.hash = '#/' + nome; };
  const nomeRotta = () => { const m = /^#\/(\w+)/.exec(location.hash); return m ? m[1] : 'mappa'; };

  function disegnaTestata(attiva) {
    const menu = $('#menu');
    menu.setAttribute('aria-label', NT.t('Sections'));
    $('#piede').textContent = NT.t('NeoTracker is not a medical tool and does not make diagnoses. For any mole that changes, bleeds, itches or worries you, see a dermatologist.');
    menu.replaceChildren(...VOCI.map(([id, testo, ico]) =>
      h('a', { href: '#/' + id, class: 'voce' + (id === attiva ? ' attiva' : ''), 'aria-current': id === attiva ? 'page' : null }, NT.icona(ico, 18), h('span', {}, testo))));
    const box = $('#utente-box');
    box.replaceChildren(S.utente
      ? h('a', { href: '#/utenti', class: 'utente-chip', title: NT.t('Switch user') }, NT.avatar(S.utente.nome, 28, S.utente),
        h('span', { class: 'utente-nome' }, S.utente.nome), h('span', { class: 'utente-cambia' }, NT.t('Change')))
      : h('a', { href: '#/utenti', class: 'utente-chip' }, h('span', { class: 'utente-nome' }, NT.t('Choose user'))));
  }

  async function route() {
    NT.pulizie.splice(0).forEach(f => { try { f(); } catch (e) { /* ignore */ } });
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
      cont.replaceChildren(h('div', { class: 'scheda errore-pagina' }, h('h2', {}, NT.t('Something went wrong')), h('p', {}, e.message || String(e)),
        h('button', { class: 'btn', onclick: () => route() }, NT.t('Try again'))));
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

  /* ---- "heartbeat": every few seconds the page tells the program "I am still open" ----
     When the window is closed the heartbeats stop (and a last "goodbye" message is sent):
     the program understands that it can shut down. Each page has a random number, so several windows
     open at the same time do not get mixed up. */
  const nuovoId = () => (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
    : String(Date.now()) + Math.random().toString(36).slice(2);
  let ID_PAGINA = nuovoId();
  NT.battitoAttivo = true;                       // becomes false after "Close NeoTracker" (it must not beat any more)
  function segnale(percorso) {
    if (!NT.battitoAttivo && percorso === '/api/battito') return;
    try {
      // keepalive: the request goes out even while the page is closing
      fetch(percorso, { method: 'POST', keepalive: true,
        headers: { 'Content-Type': 'application/json', 'X-NeoTracker': '1' },
        body: JSON.stringify({ id: ID_PAGINA }) }).catch(() => { /* program already shut down: fine */ });
    } catch (e) { /* ignore */ }
  }
  // Presence connection: it stays open as long as the page is open. When the window closes (in any way) the
  // program notices at once. It reconnects by itself if it drops.
  function apriPresenza() {
    if (NT.presenza) { try { NT.presenza.close(); } catch (e) { /* ignore */ } }
    try { NT.presenza = new EventSource('/api/presenza?id=' + encodeURIComponent(ID_PAGINA)); } catch (e) { NT.presenza = null; }
  }
  apriPresenza();
  segnale('/api/battito');
  setInterval(() => segnale('/api/battito'), 5000);
  window.addEventListener('pageshow', ev => {
    // If the browser "wakes" us from a copy set aside (ev.persisted), the program had already received the
    // goodbye: we present ourselves as a new page, with a new number.
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
      $('#vista').replaceChildren(h('div', { class: 'scheda errore-pagina' }, h('h2', {}, NT.t('NeoTracker is not responding')), h('p', {}, e.message)));
      return;
    }
    window.addEventListener('hashchange', route);
    if (!location.hash || location.hash === '#') location.hash = S.utente ? '#/mappa' : '#/utenti';
    else route();
    if (S.imp.avvertenze_accettate !== S.stato.avvertenze_versione) NT.mostraAvvertenze();     // first start (or updated notice)
  }
  avvia();
})();
