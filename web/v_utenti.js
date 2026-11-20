/* ============================================================================
   v_utenti.js - choosing and managing users (the app is multi-user)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  function dialogoNome(titolo, valore, testoOk) {
    return new Promise(res => {
      const campo = h('input', { type: 'text', class: 'campo', maxlength: 60, value: valore || '', placeholder: NT.t('Name or nickname'), autocomplete: 'off' });
      const errore = h('div', { class: 'errore-campo' });
      const invia = () => {
        const v = campo.value.trim();
        if (!v) { errore.textContent = NT.t('Type a name.'); return; }
        res(v); NT.chiudiDialogo();
      };
      campo.addEventListener('keydown', e => { if (e.key === 'Enter') invia(); });
      const d = NT.apriDialogo(h('div', {}, h('h3', {}, titolo), campo, errore,
        h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => { res(null); NT.chiudiDialogo(); } }, NT.t('Cancel')),
          h('button', { class: 'btn btn-pri', onclick: invia }, testoOk || NT.t('Save')))));
      d.addEventListener('close', () => res(null), { once: true });
      campo.focus(); campo.select();
    });
  }

  NT.viste.utenti = async function (cont) {
    S.utenti = await NT.get('/api/utenti');

    async function nuovo() {
      const nome = await dialogoNome(NT.t('New user'), '', NT.t('Create user'));
      if (!nome) return;
      try {
        const r = await NT.api('POST', '/api/utenti', { nome });
        S.utenti = await NT.get('/api/utenti');
        await NT.scegliUtente(r.id, false);
        NT.toast(NT.t('User created. Fill in the profile: it helps put the results in context.'), 'ok');
        NT.vai('profilo');
      } catch (e) { NT.errore(e); }
    }
    async function rinomina(u) {
      const nome = await dialogoNome(NT.t('Rename user'), u.nome, NT.t('Save'));
      if (!nome || nome === u.nome) return;
      try {
        await NT.api('PATCH', '/api/utenti/' + u.id, { nome });
        if (S.utente && S.utente.id === u.id) await NT.ricaricaUtente();
        NT.vai('utenti');
      } catch (e) { NT.errore(e); }
    }
    async function elimina(u) {
      const si = await NT.conferma(NT.t('Delete «{nome}»?', { nome: u.nome }),
        NT.t('The profile, all moles, all photos and all reports of this user will be deleted permanently. This cannot be undone.'),
        { si: NT.t('Delete permanently'), pericolo: true, scrivi: u.nome });
      if (!si) return;
      try {
        await NT.api('DELETE', '/api/utenti/' + u.id, { conferma: u.nome });
        if (S.utente && S.utente.id === u.id) { S.utente = null; S.nei = []; NT.ls.scrivi('nt_utente', ''); }
        NT.toast(NT.t('User deleted.'), 'ok');
        NT.vai('utenti');
      } catch (e) { NT.errore(e); }
    }

    const schede = S.utenti.map(u => h('div', { class: 'utente-card' + (S.utente && S.utente.id === u.id ? ' corrente' : '') },
      h('button', { class: 'utente-apri', onclick: () => NT.scegliUtente(u.id).catch(NT.errore) },
        NT.avatar(u.nome, 56, u),
        h('span', { class: 'utente-info' }, h('strong', {}, u.nome),
          h('span', { class: 'sotto' }, NT.tp(u.n_nevi, '{n} mole', '{n} moles') + (u.eta !== null && u.eta !== undefined ? ' · ' + NT.tp(u.eta, '{n} year', '{n} years') : '')))),
      h('div', { class: 'utente-azioni' },
        h('button', { class: 'btn-testo', onclick: () => rinomina(u) }, NT.t('Rename')),
        h('button', { class: 'btn-testo pericolo', onclick: () => elimina(u) }, NT.t('Delete')))));

    cont.replaceChildren(h('div', { class: 'pagina stretta' },
      h('h1', {}, S.utenti.length ? NT.t('Who are you?') : NT.t('Welcome to NeoTracker')),
      h('p', { class: 'lead' }, S.utenti.length
        ? NT.t('Choose your profile: each person has their own mole map, photos and data.')
        : NT.t('This program helps you keep track of your moles over time: you mark them on a body map, keep their photos with the date and have them analysed by several methods. Start by creating your user.')),
      h('div', { class: 'utenti-griglia' }, schede,
        h('button', { class: 'utente-card nuovo', onclick: nuovo }, h('span', { class: 'piu' }, NT.icona('piu', 28)), h('strong', {}, NT.t('New user')))),
      h('div', { class: 'nota-privacy' }, NT.icona('ok', 16),
        h('span', {}, NT.t('All data stays on this computer, in the folder:') + ' ', h('code', {}, S.stato.cartella_dati || ''),
          ' ' + NT.t('Nothing is sent online, except the requests you turn on (UV weather, PubMed literature, SkinSense).')))));
  };
})();
