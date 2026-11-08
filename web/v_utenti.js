/* ============================================================================
   v_utenti.js - scelta e gestione degli utenti (l'app e' multi-utente)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  function dialogoNome(titolo, valore, testoOk) {
    return new Promise(res => {
      const campo = h('input', { type: 'text', class: 'campo', maxlength: 60, value: valore || '', placeholder: 'Nome o soprannome', autocomplete: 'off' });
      const errore = h('div', { class: 'errore-campo' });
      const invia = () => {
        const v = campo.value.trim();
        if (!v) { errore.textContent = 'Scrivi un nome.'; return; }
        res(v); NT.chiudiDialogo();
      };
      campo.addEventListener('keydown', e => { if (e.key === 'Enter') invia(); });
      const d = NT.apriDialogo(h('div', {}, h('h3', {}, titolo), campo, errore,
        h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => { res(null); NT.chiudiDialogo(); } }, 'Annulla'),
          h('button', { class: 'btn btn-pri', onclick: invia }, testoOk || 'Salva'))));
      d.addEventListener('close', () => res(null), { once: true });
      campo.focus(); campo.select();
    });
  }

  NT.viste.utenti = async function (cont) {
    S.utenti = await NT.get('/api/utenti');

    async function nuovo() {
      const nome = await dialogoNome('Nuovo utente', '', 'Crea utente');
      if (!nome) return;
      try {
        const r = await NT.api('POST', '/api/utenti', { nome });
        S.utenti = await NT.get('/api/utenti');
        await NT.scegliUtente(r.id, false);
        NT.toast('Utente creato. Compila il profilo: serve a contestualizzare i risultati.', 'ok');
        NT.vai('profilo');
      } catch (e) { NT.errore(e); }
    }
    async function rinomina(u) {
      const nome = await dialogoNome('Rinomina utente', u.nome, 'Salva');
      if (!nome || nome === u.nome) return;
      try {
        await NT.api('PATCH', '/api/utenti/' + u.id, { nome });
        if (S.utente && S.utente.id === u.id) await NT.ricaricaUtente();
        NT.vai('utenti');
      } catch (e) { NT.errore(e); }
    }
    async function elimina(u) {
      const si = await NT.conferma('Eliminare «' + u.nome + '»?',
        'Verranno cancellati per sempre il profilo, tutti i nei, tutte le foto e tutti i rapporti di questo utente. L\'operazione non si può annullare.',
        { si: 'Elimina definitivamente', pericolo: true, scrivi: u.nome });
      if (!si) return;
      try {
        await NT.api('DELETE', '/api/utenti/' + u.id, { conferma: u.nome });
        if (S.utente && S.utente.id === u.id) { S.utente = null; S.nei = []; NT.ls.scrivi('nt_utente', ''); }
        NT.toast('Utente eliminato.', 'ok');
        NT.vai('utenti');
      } catch (e) { NT.errore(e); }
    }

    const schede = S.utenti.map(u => h('div', { class: 'utente-card' + (S.utente && S.utente.id === u.id ? ' corrente' : '') },
      h('button', { class: 'utente-apri', onclick: () => NT.scegliUtente(u.id).catch(NT.errore) },
        NT.avatar(u.nome, 56, u),
        h('span', { class: 'utente-info' }, h('strong', {}, u.nome),
          h('span', { class: 'sotto' }, u.n_nevi + (u.n_nevi === 1 ? ' neo' : ' nei') + (u.eta !== null && u.eta !== undefined ? ' · ' + u.eta + ' anni' : '')))),
      h('div', { class: 'utente-azioni' },
        h('button', { class: 'btn-testo', onclick: () => rinomina(u) }, 'Rinomina'),
        h('button', { class: 'btn-testo pericolo', onclick: () => elimina(u) }, 'Elimina'))));

    cont.replaceChildren(h('div', { class: 'pagina stretta' },
      h('h1', {}, S.utenti.length ? 'Chi sei?' : 'Benvenuto in NeoTracker'),
      h('p', { class: 'lead' }, S.utenti.length
        ? 'Scegli il tuo profilo: ogni persona ha la propria mappa dei nei, le proprie foto e i propri dati.'
        : 'Questo programma ti aiuta a tenere traccia dei tuoi nei nel tempo: li segni su una mappa del corpo, ne conservi le foto con la data e li fai analizzare da più metodi. Inizia creando il tuo utente.'),
      h('div', { class: 'utenti-griglia' }, schede,
        h('button', { class: 'utente-card nuovo', onclick: nuovo }, h('span', { class: 'piu' }, NT.icona('piu', 28)), h('strong', {}, 'Nuovo utente'))),
      h('div', { class: 'nota-privacy' }, NT.icona('ok', 16),
        h('span', {}, 'Tutti i dati restano su questo computer, nella cartella ', h('code', {}, S.stato.cartella_dati || ''),
          '. Nulla viene inviato online, tranne le richieste che attivi tu (meteo UV, letteratura PubMed, SkinSense).'))));
  };
})();
