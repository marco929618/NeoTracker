/* ============================================================================
   v_mappa.js - body map, list of moles, photo history and analysis
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h, $ = NT.$;

  const SEDI_UTILI = [NT.m('palm of the hand'), NT.m('back of the hand'), NT.m('sole of the foot'), NT.m('top of the foot'), NT.m('between the fingers or toes'),
    NT.m('under the nail (hand)'), NT.m('under the nail (foot)'), NT.m('scalp'), NT.m('ear'), NT.m('eyelid'), NT.m('lip')];
  const GIORNI_PROMEMORIA = 90;

  let mappa = null, modo = 'lista', bozza = null, dett = null, fotoSel = null, pollTimer = null;
  let etichettaRegione = null, panel = null, formFotoAperto = false, sedeBozzaManuale = false;
  const inAnalisi = new Set();

  const nomiAuto = () => new Set(['fronte', 'retro'].flatMap(v => window.Corpo.regioni(v).map(r => r.nome)));
  /* The sites from the map and the suggested ones are always saved in English (so they work in every language);
     the user sees and types them in his/her own language: here we go back from the translated text to the English one. */
  const sedeCanonica = (() => {
    let inverso = null;
    return testo => {
      const v = String(testo || '').trim();
      if (NT.lingua === 'en') return v;
      if (!inverso) inverso = new Map([...nomiAuto(), ...SEDI_UTILI].map(s => [NT.tr(s), s]));
      return inverso.get(v) || v;
    };
  })();
  const opzioniSedi = () => SEDI_UTILI.map(s => h('option', { value: NT.tr(s) }));
  const attivi = () => S.nei.filter(n => !n.archiviato);
  const numDi = id => { const i = attivi().findIndex(n => n.id === id); return i < 0 ? '–' : i + 1; };

  function datiMarcatori() {
    return S.nei.map(n => ({
      id: n.id, vista: n.vista, x: n.x, y: n.y, nome: n.nome, archiviato: !!n.archiviato,
      num: numDi(n.id), flag: n.ultimo_esito === 'attenzione' || n.ultimo_esito === 'discordante', senzaFoto: n.n_foto === 0,
    }));
  }
  function aggiornaMarcatori() {
    if (mappa) mappa.setNei(datiMarcatori(), modo === 'neo' && dett ? dett.nevo.id : null);
  }
  function stopPoll() { clearTimeout(pollTimer); pollTimer = null; }

  /* ======================================================================== */
  NT.viste.mappa = async function (cont) {
    await NT.ricaricaNei();
    modo = 'lista'; bozza = null; dett = null; fotoSel = null; formFotoAperto = false; sedeBozzaManuale = false;
    inAnalisi.clear();

    const btnAggiungi = h('button', { class: 'btn btn-pri', id: 'btn-aggiungi', onclick: () => attivaAggiunta(!(mappa && mappa.aggiunta)) },
      NT.icona('mirino', 18), NT.t('Add mole'));
    const suggerimento = h('span', { class: 'mappa-hint', id: 'mappa-hint' }, NT.t('Wheel = zoom · drag = move · double click = enlarge'));
    const barra = h('div', { class: 'mappa-barra' }, btnAggiungi, suggerimento,
      h('span', { class: 'spazio' }),
      h('button', { class: 'btn-icona', title: NT.t('Zoom out'), onclick: () => mappa.zoomSu(1 / 1.5) }, NT.icona('meno')),
      h('button', { class: 'btn-icona', title: NT.t('Enlarge'), onclick: () => mappa.zoomSu(1.5) }, NT.icona('piu')),
      h('button', { class: 'btn-icona', title: NT.t('Show the whole body'), onclick: () => mappa.reset() }, NT.icona('reset')));
    const box = h('div', { class: 'mappa-box' });
    etichettaRegione = h('div', { class: 'regione-etichetta' }, NT.t('Move the pointer over the body to see the area'));
    const legenda = h('div', { class: 'legenda' },
      h('span', {}, h('i', { class: 'pallino pieno' }), NT.t('Mole with photos')),
      h('span', {}, h('i', { class: 'pallino vuoto' }), NT.t('No photos yet')),
      h('span', {}, h('i', { class: 'pallino rosso' }), NT.t('Analysis: needs attention')),
      h('span', { class: 'lato-nota' }, NT.t("R = patient's right · L = left")));
    panel = h('aside', { class: 'pannello', 'aria-live': 'polite' });
    cont.replaceChildren(h('div', { class: 'mappa-layout' }, h('section', { class: 'scheda mappa-scheda' }, barra, box, etichettaRegione, legenda), panel));

    mappa = new window.Corpo.MappaCorpo(box, {
      onRegione: nome => { etichettaRegione.textContent = nome ? NT.tr(nome) : NT.t('Move the pointer over the body to see the area'); },
      onPunto: nuovoPunto, onSeleziona: id => { if (id) selezionaNeo(id); else if (modo !== 'bozza') tornaLista(); },
      onSposta: spostaNeo, onBozzaMossa: p => { bozza = Object.assign({}, bozza, p); if (!sedeBozzaManuale) aggiornaSedeBozza(); },
    });
    mappa.setFototipo((S.utente.profilo && S.utente.profilo.fototipo) || 0);
    aggiornaMarcatori();
    renderPannello();
    NT.alCambioPagina(() => { stopPoll(); if (mappa && mappa.ro) mappa.ro.disconnect(); mappa = null; });
  };

  function attivaAggiunta(on) {
    if (!mappa) return;
    if (on) { bozza = null; dett = null; modo = 'lista'; mappa.setSelezione(null); }
    mappa.modalitaAggiunta(on);
    const b = $('#btn-aggiungi');
    if (b) b.classList.toggle('attivo', on);
    const hint = $('#mappa-hint');
    if (hint) hint.textContent = on ? NT.t('Click on the exact spot on the body where the mole is (you can zoom in first)') : NT.t('Wheel = zoom · drag = move · double click = enlarge');
    if (on) { aggiornaMarcatori(); renderPannello(); }
  }

  function tornaLista() {
    stopPoll(); modo = 'lista'; dett = null; fotoSel = null; bozza = null;
    if (mappa) { mappa.modalitaAggiunta(false); }
    attivaAggiunta(false);
    aggiornaMarcatori(); renderPannello();
  }

  /* ---------------------------- new mole ---------------------------------- */
  function nuovoPunto(p) {
    bozza = { vista: p.vista, x: p.x, y: p.y, regione: p.regione };
    modo = 'bozza'; sedeBozzaManuale = false;
    mappa.modalitaAggiunta(false);
    const b = $('#btn-aggiungi'); if (b) b.classList.remove('attivo');
    mappa.setBozza(bozza);
    renderPannello();
  }
  function aggiornaSedeBozza() {
    const c = $('#campo-sede-bozza');
    if (c && bozza) c.value = bozza.regione ? NT.tr(bozza.regione) : '';
    const info = $('#info-pos-bozza');
    if (info && bozza) info.textContent = testoPos(bozza);
  }
  const testoPos = p => NT.t('{vista} · position {x}% from the left, {y}% from the top',
    { vista: p.vista === 'fronte' ? NT.t('Front') : NT.t('Back'), x: Math.round(p.x * 100), y: Math.round(p.y * 100) });

  function pannelloBozza() {
    const nome = h('input', { type: 'text', class: 'campo', maxlength: 60, value: NT.t('Mole {n}', { n: S.nei.length + 1 }), id: 'campo-nome-bozza' });
    const sede = h('input', { type: 'text', class: 'campo', maxlength: 80, list: 'sedi-utili', value: bozza.regione ? NT.tr(bozza.regione) : '', id: 'campo-sede-bozza',
      oninput: () => { sedeBozzaManuale = true; } });
    const note = h('textarea', { class: 'campo', rows: 3, maxlength: 1000, placeholder: NT.t('When you noticed it, whether it itches, whether it has changed…') });
    const salva = h('button', { class: 'btn btn-pri', onclick: async () => {
      salva.disabled = true;
      try {
        const r = await NT.api('POST', '/api/utenti/' + S.utente.id + '/nevi',
          { nome: nome.value, vista: bozza.vista, x: bozza.x, y: bozza.y, regione: sedeCanonica(sede.value), note: note.value });
        await NT.ricaricaNei();
        bozza = null; mappa.setBozza(null);
        formFotoAperto = true;
        await selezionaNeo(r.id);
        NT.toast(NT.t('Mole saved. Now add the first photo: it will be your "baseline photo".'), 'ok');
      } catch (e) { salva.disabled = false; NT.errore(e); }
    } }, NT.t('Save mole'));
    return h('div', { class: 'scheda' },
      h('h2', {}, NT.t('New mole')),
      h('p', { class: 'piccolo', id: 'info-pos-bozza' }, testoPos(bozza)),
      h('p', { class: 'piccolo' }, NT.icona('mirino', 14), ' ' + NT.t('Drag the dot on the map to correct the position; zoom in with the wheel for maximum precision.')),
      h('label', { class: 'etichetta' }, NT.t('Name'), nome),
      h('label', { class: 'etichetta' }, NT.t('Site (editable)'), sede,
        h('datalist', { id: 'sedi-utili' }, opzioniSedi())),
      h('label', { class: 'etichetta' }, NT.t('Notes'), note),
      h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => tornaLista() }, NT.t('Cancel')), salva));
  }

  /* ------------------------- moving a mole -------------------------- */
  async function spostaNeo(id, p) {
    const n = S.nei.find(q => q.id === id);
    if (!n) return;
    const corpo = { vista: p.vista, x: p.x, y: p.y };
    if (p.regione && (!n.regione || nomiAuto().has(n.regione))) corpo.regione = p.regione;
    try {
      await NT.api('PATCH', '/api/nevi/' + id, corpo);
      await NT.ricaricaNei();
      if (dett && dett.nevo.id === id) dett = await NT.get('/api/nevi/' + id);
      aggiornaMarcatori(); renderPannello();
      NT.toast(corpo.regione ? NT.t('Location updated: {regione}.', { regione: NT.tr(corpo.regione) }) : NT.t('Location updated.'), 'ok');
    } catch (e) { NT.errore(e); await NT.ricaricaNei(); aggiornaMarcatori(); }
  }

  /* --------------------------- selecting a mole -------------------------- */
  async function selezionaNeo(id, centra) {
    stopPoll();
    try { dett = await NT.get('/api/nevi/' + id); } catch (e) { NT.errore(e); return; }
    modo = 'neo'; bozza = null;
    fotoSel = dett.foto.length ? dett.foto[dett.foto.length - 1].id : null;
    if (mappa) { mappa.modalitaAggiunta(false); mappa.setBozza(null); }
    const b = $('#btn-aggiungi'); if (b) b.classList.remove('attivo');
    aggiornaMarcatori();
    if (centra && mappa) mappa.centraSu(dett.nevo, 4);
    renderPannello();
  }
  async function ricaricaDettaglio() {
    dett = await NT.get('/api/nevi/' + dett.nevo.id);
    await NT.ricaricaNei();
    aggiornaMarcatori();
  }

  /* ============================== PANEL ================================== */
  function renderPannello() {
    if (!panel) return;
    stopPoll();
    const top = panel.scrollTop;
    panel.replaceChildren(modo === 'bozza' && bozza ? pannelloBozza() : modo === 'neo' && dett ? pannelloNeo() : pannelloLista());
    panel.scrollTop = modo === 'neo' ? top : 0;
    if (modo === 'neo' && fotoSel) caricaAnalisi(fotoSel);
  }

  /* ------------------------------ list of moles ----------------------------- */
  function schedaLista(n) {
    const giorni = n.giorni_da_ultima;
    const promemoria = giorni !== null && giorni >= GIORNI_PROMEMORIA && !n.archiviato;
    return h('button', { class: 'neo-card', onclick: () => selezionaNeo(n.id, true) },
      h('span', { class: 'neo-num' + (n.n_foto === 0 ? ' vuoto' : '') + (n.ultimo_esito === 'attenzione' || n.ultimo_esito === 'discordante' ? ' rosso' : '') }, numDi(n.id)),
      n.ultima_foto_id ? h('img', { class: 'neo-thumb', src: '/foto/' + n.ultima_foto_id + '/mini?l=120', alt: '', loading: 'lazy' }) : h('span', { class: 'neo-thumb vuota' }, NT.icona('foto', 22)),
      h('span', { class: 'neo-info' },
        h('strong', {}, n.nome),
        h('span', { class: 'sotto' }, n.regione ? NT.tr(n.regione) : (n.vista === 'fronte' ? NT.t('Front') : NT.t('Back'))),
        h('span', { class: 'sotto' }, n.n_foto === 0 ? NT.t('No photos: add the first one')
          : NT.t('{foto} · last {quando}', { foto: NT.tp(n.n_foto, '{n} photo', '{n} photos'), quando: NT.fraseGiorni(giorni) })),
        h('span', { class: 'chips' }, NT.chipEsito(n.ultimo_esito), promemoria ? h('span', { class: 'chip chip-neutro' }, NT.t('Time to re-photograph?')) : null)));
  }

  function pannelloLista() {
    const lista = attivi(), arch = S.nei.filter(n => n.archiviato);
    const vuoto = !S.nei.length;
    return h('div', { class: 'scheda' },
      h('div', { class: 'testa-lista' }, h('h2', {}, vuoto ? NT.t('No moles yet') : NT.t('Your moles ({n})', { n: lista.length })),
        lista.length ? h('button', { class: 'btn-testo', title: NT.t('Print a sheet with all the moles'), onclick: () => NT.stampaNei(lista.map(n => n.id)) }, NT.icona('stampa', 16), NT.t('Sheet for the dermatologist')) : null),
      vuoto
        ? h('ol', { class: 'passi' },
          h('li', {}, NT.t('Press'), ' ', h('strong', {}, NT.t('Add mole')), ' ' + NT.t('and click on the exact spot on the body (zoom in with the wheel to be more precise).')),
          h('li', {}, NT.t('Give the mole a name and check the site.')),
          h('li', {}, NT.t('Add the first photo: it becomes your baseline photo, and every later photo will follow how the mole evolves.')))
        : h('div', { class: 'neo-elenco' }, lista.map(schedaLista)),
      arch.length ? h('details', { class: 'archiviati' }, h('summary', {}, NT.t('Archived moles ({n})', { n: arch.length })),
        arch.map(n => h('div', { class: 'riga-arch' }, h('span', {}, n.nome + (n.regione ? ' – ' + NT.tr(n.regione) : '')),
          h('button', { class: 'btn-testo', onclick: async () => { try { await NT.api('PATCH', '/api/nevi/' + n.id, { archiviato: false }); await NT.ricaricaNei(); aggiornaMarcatori(); renderPannello(); } catch (e) { NT.errore(e); } } }, NT.t('Restore'))))) : null,
      !vuoto ? h('p', { class: 'piccolo muted' }, NT.t('Click a mole in the list or on the map to see its photo history.')) : null);
  }

  /* ------------------------------ mole detail ------------------------------ */
  function pannelloNeo() {
    const n = dett.nevo, foto = dett.foto;
    const salva = async (campi) => { try { await NT.api('PATCH', '/api/nevi/' + n.id, campi); await ricaricaDettaglio(); } catch (e) { NT.errore(e); } };

    const nome = h('input', { type: 'text', class: 'campo titolo-modifica', maxlength: 60, value: n.nome, 'aria-label': NT.t('Mole name'),
      onchange: () => { if (nome.value.trim()) salva({ nome: nome.value }); else nome.value = n.nome; } });
    const sede = h('input', { type: 'text', class: 'campo', maxlength: 80, list: 'sedi-utili', value: n.regione ? NT.tr(n.regione) : '', placeholder: NT.t('Site'),
      onchange: () => salva({ regione: sedeCanonica(sede.value) }) });
    const note = h('textarea', { class: 'campo', rows: 2, maxlength: 1000, placeholder: NT.t('Notes on the mole…'), onchange: () => salva({ note: note.value }) }, n.note);

    const testa = h('div', { class: 'scheda' },
      h('div', { class: 'neo-testa' },
        h('button', { class: 'btn-testo', onclick: () => tornaLista() }, NT.t('← All moles')),
        h('span', { class: 'spazio' }),
        h('button', { class: 'btn-icona', title: NT.t('Centre on the map'), onclick: () => mappa.centraSu(n, 5) }, NT.icona('mirino')),
        h('button', { class: 'btn-icona', title: NT.t('Print the sheet for this mole'), onclick: () => NT.stampaNei([n.id]) }, NT.icona('stampa')),
        h('button', { class: 'btn-icona', title: NT.t('Archive (removes it from the map, keeps the data)'), onclick: async () => {
          await salva({ archiviato: true }); tornaLista(); NT.toast(NT.t('Mole archived. You will find it at the bottom of the list.'), 'ok'); } }, NT.icona('archivio')),
        h('button', { class: 'btn-icona pericolo', title: NT.t('Delete this mole and its photos'), onclick: async () => {
          const si = await NT.conferma(NT.t('Delete «{nome}»?', { nome: n.nome }),
            NT.tp(foto.length, 'Its only photo and the analysis reports will be deleted permanently.', 'All its {n} photos and the analysis reports will be deleted permanently.'),
            { si: NT.t('Delete'), pericolo: true, scrivi: foto.length ? n.nome : null });
          if (!si) return;
          try { await NT.api('DELETE', '/api/nevi/' + n.id); await NT.ricaricaNei(); tornaLista(); NT.toast(NT.t('Mole deleted.'), 'ok'); } catch (e) { NT.errore(e); } } }, NT.icona('cestino'))),
      h('div', { class: 'neo-titolo' }, h('span', { class: 'neo-num grande' + (foto.length ? '' : ' vuoto') }, numDi(n.id)), nome),
      h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, NT.t('Site'), sede,
        h('datalist', { id: 'sedi-utili' }, opzioniSedi())),
        h('div', { class: 'etichetta' }, NT.t('Location'), h('div', { class: 'piccolo' }, testoPos(n), h('br'), NT.t('Drag the dot on the map to move it.')))),
      h('label', { class: 'etichetta' }, NT.t('Notes'), note));

    const sezioni = [testa, sezioneStorico(n, foto), formFoto(n)];
    const grafico = graficoDiametro(foto);
    if (grafico) sezioni.push(grafico);
    sezioni.push(h('div', { class: 'scheda', id: 'box-analisi' }, h('h3', {}, NT.t('Automatic analysis')), NT.caricamento(NT.t('Checking status…'))));
    return h('div', { class: 'pila' }, sezioni);
  }

  /* ----------------------------- photo history ----------------------------- */
  function sezioneStorico(n, foto) {
    if (!foto.length) {
      return h('div', { class: 'scheda' }, h('h3', {}, NT.t('Photo history')),
        NT.vuoto(NT.t('No photos yet'), NT.t('Add the first photo below: it will be the starting point to see whether the mole changes over time.')));
    }
    const f = foto.find(x => x.id === fotoSel) || foto[foto.length - 1];
    const striscia = h('div', { class: 'striscia' }, foto.map(x => h('button', { class: 'miniatura' + (x.id === f.id ? ' sel' : ''), title: NT.fmtData(x.scattata_il) + (x.diametro_mm ? ' · ' + NT.num(x.diametro_mm) + ' mm' : ''),
      onclick: () => { fotoSel = x.id; renderPannello(); } },
      h('img', { src: '/foto/' + x.id + '/mini?l=240', alt: NT.t('Photo from {data}', { data: NT.fmtData(x.scattata_il) }), loading: 'lazy' }),
      h('span', { class: 'data' }, NT.fmtData(x.scattata_il)),
      x.esito && x.esito !== 'nessuno' ? h('i', { class: 'punto-esito ' + NT.ESITI[x.esito].cls, title: NT.ESITI[x.esito].testo }) : null)));
    const precedente = foto[foto.indexOf(f) - 1];
    const meta = h('div', { class: 'foto-meta' },
      h('span', {}, h('strong', {}, NT.fmtData(f.scattata_il)), ' · ', f.tipo === 'dermoscopica' ? NT.t('dermoscopic') : NT.t('normal photo')),
      f.diametro_mm ? h('span', {}, NT.t('Diameter:') + ' ', h('strong', {}, NT.num(f.diametro_mm) + ' mm'),
        precedente && precedente.diametro_mm ? h('span', { class: 'delta' }, ' ' + NT.t('({variazione} mm since the previous photo)', { variazione: (f.diametro_mm - precedente.diametro_mm >= 0 ? '+' : '') + NT.num(f.diametro_mm - precedente.diametro_mm) })) : null) : null,
      f.note ? h('span', { class: 'muted' }, f.note) : null);
    return h('div', { class: 'scheda' },
      h('div', { class: 'testa-lista' }, h('h3', {}, NT.t('Photo history ({n})', { n: foto.length })),
        foto.length >= 2 ? h('button', { class: 'btn-testo', onclick: () => dialogoConfronto(foto, f) }, NT.icona('confronta', 16), NT.t('Compare')) : null),
      striscia,
      h('button', { class: 'anteprima', title: NT.t('Click to see the original photo full screen'), onclick: () => apriLightbox(f) },
        h('img', { src: '/foto/' + f.id + '/mini?l=960', alt: NT.t('Photo from {data}', { data: NT.fmtData(f.scattata_il) }) })),
      meta,
      h('div', { class: 'azioni-foto' },
        h('button', { class: 'btn-testo', onclick: () => dialogoModificaFoto(f) }, NT.t('Edit date/measurement')),
        h('button', { class: 'btn-testo pericolo', onclick: async () => {
          const si = await NT.conferma(NT.t('Delete this photo?'), NT.t('The photo from {data} and its analysis report will be deleted permanently.', { data: NT.fmtData(f.scattata_il) }), { si: NT.t('Delete photo'), pericolo: true });
          if (!si) return;
          try { await NT.api('DELETE', '/api/foto/' + f.id); await ricaricaDettaglio(); fotoSel = dett.foto.length ? dett.foto[dett.foto.length - 1].id : null; renderPannello(); NT.toast(NT.t('Photo deleted.'), 'ok'); } catch (e) { NT.errore(e); } } }, NT.t('Delete photo'))));
  }

  function apriLightbox(f) {
    const d = $('#lightbox');
    d.replaceChildren(h('div', { class: 'lb' },
      h('div', { class: 'lb-barra' }, h('strong', {}, NT.fmtData(f.scattata_il)), h('span', { class: 'spazio' }), h('button', { class: 'btn', onclick: () => d.close() }, NT.t('Close'))),
      h('img', { src: '/foto/' + f.id + '/originale', alt: NT.t('Original photo') })));
    d.showModal();
  }

  function dialogoModificaFoto(f) {
    const data = h('input', { type: 'date', class: 'campo', value: f.scattata_il, max: NT.oggiISO() });
    const diam = h('input', { type: 'text', class: 'campo', inputmode: 'decimal', value: f.diametro_mm === null ? '' : NT.num(f.diametro_mm), placeholder: NT.t('e.g. 4.5') });
    const tipo = h('select', { class: 'campo' }, h('option', { value: 'normale', selected: f.tipo === 'normale' }, NT.t('Normal photo')), h('option', { value: 'dermoscopica', selected: f.tipo === 'dermoscopica' }, NT.t('Dermoscopic')));
    const nota = h('textarea', { class: 'campo', rows: 2, maxlength: 1000 }, f.note);
    NT.apriDialogo(h('div', {}, h('h3', {}, NT.t('Edit photo')),
      h('label', { class: 'etichetta' }, NT.t('Date the photo was taken'), data), h('label', { class: 'etichetta' }, NT.t('Diameter (mm)'), diam),
      h('label', { class: 'etichetta' }, NT.t('Type'), tipo), h('label', { class: 'etichetta' }, NT.t('Notes'), nota),
      h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => NT.chiudiDialogo() }, NT.t('Cancel')),
        h('button', { class: 'btn btn-pri', onclick: async () => {
          try {
            await NT.api('PATCH', '/api/foto/' + f.id, { scattata_il: data.value, diametro_mm: diam.value, tipo: tipo.value, note: nota.value });
            NT.chiudiDialogo(); await ricaricaDettaglio(); renderPannello();
          } catch (e) { NT.errore(e); }
        } }, NT.t('Save')))));
  }

  /* ----------------------------- adding a photo ----------------------------- */
  function formFoto(n) {
    let file = null;
    const anteprima = h('div', { class: 'drop-testo' }, NT.icona('foto', 26), h('span', {}, NT.t('Drag a photo here or click to choose one')), h('small', {}, NT.t('JPG, PNG, WEBP or BMP · up to 60 MB')));
    const input = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/bmp,.jpg,.jpeg,.png,.webp,.bmp', class: 'nascosto' });
    const drop = h('label', { class: 'drop' }, input, anteprima);
    const data = h('input', { type: 'date', class: 'campo', value: NT.oggiISO(), max: NT.oggiISO(), oninput: () => { usaExif.checked = false; } });
    const usaExif = h('input', { type: 'checkbox', checked: true });
    const tipo = h('select', { class: 'campo' }, h('option', { value: 'normale' }, NT.t('Normal photo (smartphone)')), h('option', { value: 'dermoscopica' }, NT.t('Dermoscopic')));
    const diam = h('input', { type: 'text', class: 'campo', inputmode: 'decimal', placeholder: NT.t('e.g. 4.5') });
    const nota = h('input', { type: 'text', class: 'campo', maxlength: 1000, placeholder: NT.t('Optional') });
    const analizza = h('input', { type: 'checkbox', checked: true });
    const btn = h('button', { class: 'btn btn-pri', disabled: true }, NT.icona('foto', 18), NT.t('Save photo'));

    function scegli(fl) {
      if (!fl) return;
      if (!/^image\//.test(fl.type) && !/\.(jpe?g|png|webp|bmp)$/i.test(fl.name)) { NT.toast(NT.t('Choose an image file (JPG, PNG, WEBP or BMP).'), 'errore'); return; }
      if (fl.size > (S.stato.max_mb_foto || 60) * 1048576) { NT.toast(NT.t('The photo exceeds {mb} MB: reduce it or choose another one.', { mb: S.stato.max_mb_foto || 60 }), 'errore'); return; }
      file = fl;
      data.value = NT.dataDaMs(fl.lastModified); usaExif.checked = true;
      const url = URL.createObjectURL(fl);
      anteprima.replaceChildren(h('img', { src: url, alt: NT.t('Preview'), class: 'drop-img' }), h('small', {}, NT.t('{nome} · {mb} MB · click to change', { nome: fl.name, mb: NT.num(fl.size / 1048576) })));
      btn.disabled = false;
    }
    input.addEventListener('change', () => scegli(input.files[0]));
    ['dragenter', 'dragover'].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.add('sopra'); }));
    ['dragleave', 'drop'].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.remove('sopra'); }));
    drop.addEventListener('drop', ev => scegli(ev.dataTransfer.files[0]));

    btn.addEventListener('click', async () => {
      if (!file) return;
      btn.disabled = true; btn.replaceChildren(h('span', { class: 'spinner' }), NT.t('Saving…'));
      const q = new URLSearchParams({ data: data.value, exif: usaExif.checked ? '1' : '0', tipo: tipo.value, diametro: diam.value, note: nota.value, analizza: analizza.checked ? '1' : '0' });
      try {
        const r = await NT.api('POST', '/api/nevi/' + n.id + '/foto?' + q.toString(), null, { raw: file, tipo: file.type || 'application/octet-stream' });
        formFotoAperto = false;
        await ricaricaDettaglio();
        fotoSel = r.id;
        renderPannello();
        NT.toast((r.da_exif ? NT.t('Photo saved ({data}, date read from the photo).', { data: NT.fmtData(r.scattata_il) }) : NT.t('Photo saved ({data}).', { data: NT.fmtData(r.scattata_il) }))
          + (r.analisi_errore ? ' ' + NT.tr(r.analisi_errore) : ''), r.analisi_errore ? 'errore' : 'ok');
      } catch (e) { btn.disabled = false; btn.replaceChildren(NT.icona('foto', 18), NT.t('Save photo')); NT.errore(e); }
    });

    const det = h('details', { class: 'scheda form-foto', open: formFotoAperto || dett.foto.length === 0 },
      h('summary', {}, NT.icona('piu', 16), NT.t('Add a photo to the history')),
      h('div', { class: 'form-corpo' }, drop,
        h('div', { class: 'riga-2' },
          h('label', { class: 'etichetta' }, NT.t('Date the photo was taken'), data,
            h('span', { class: 'spunta' }, usaExif, ' ' + NT.t('Use the date written in the photo, if there is one'))),
          h('label', { class: 'etichetta' }, NT.t('Measured diameter (mm)'), diam)),
        h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, NT.t('Photo type'), tipo), h('label', { class: 'etichetta' }, NT.t('Notes'), nota)),
        h('label', { class: 'spunta grande' }, analizza, ' ' + NT.t('Analyse now with all installed methods')),
        h('details', { class: 'consigli' }, h('summary', {}, NT.t('How to take comparable photos')),
          h('ul', {}, h('li', {}, NT.t('Same light (daylight, no flash) and same distance every time, about 10–15 cm.')),
            h('li', {}, NT.t('Place a ruler or a coin next to the mole: it is used to measure the diameter.')),
            h('li', {}, NT.t('In-focus photo, with the mole in the centre and the skin clearly visible (move hair aside if needed).')),
            h('li', {}, NT.t('Always shoot from the same angle and keep the original, without filters.')))),
        btn));
    return det;
  }

  /* ------------------------------ diameter chart ------------------------------ */
  function graficoDiametro(foto) {
    const pt = foto.filter(f => f.diametro_mm !== null && f.diametro_mm !== undefined).map(f => ({ d: f.scattata_il, v: f.diametro_mm }));
    if (pt.length < 2) return null;
    const L = 380, A = 190, ml = 36, mr = 14, mt = 14, mb = 32;
    const t0 = new Date(pt[0].d + 'T12:00:00').getTime(), t1 = new Date(pt[pt.length - 1].d + 'T12:00:00').getTime();
    const vmax = Math.max(7, Math.ceil(Math.max(...pt.map(p => p.v)) + 1));
    const X = d => ml + (t1 === t0 ? (L - ml - mr) / 2 : (new Date(d + 'T12:00:00').getTime() - t0) / (t1 - t0) * (L - ml - mr));
    const Y = v => A - mb - v / vmax * (A - mb - mt);
    const passo = vmax <= 10 ? 2 : 5;
    let s = '<svg viewBox="0 0 ' + L + ' ' + A + '" class="grafico" role="img" aria-label="' + NT.esc(NT.t('Mole diameter over time')) + '">';
    for (let v = 0; v <= vmax; v += passo) s += '<line x1="' + ml + '" x2="' + (L - mr) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" class="gl"/><text x="' + (ml - 6) + '" y="' + (Y(v) + 4) + '" text-anchor="end" class="gt">' + v + '</text>';
    s += '<line x1="' + ml + '" x2="' + (L - mr) + '" y1="' + Y(6) + '" y2="' + Y(6) + '" class="g6"/><text x="' + (L - mr) + '" y="' + (Y(6) - 4) + '" text-anchor="end" class="gt g6t">6 mm</text>';
    s += '<polyline class="gline" points="' + pt.map(p => X(p.d) + ',' + Y(p.v)).join(' ') + '"/>';
    pt.forEach(p => { s += '<circle cx="' + X(p.d) + '" cy="' + Y(p.v) + '" r="4.5" class="gp"><title>' + NT.fmtData(p.d) + ': ' + NT.num(p.v) + ' mm</title></circle>'; });
    s += '<text x="' + X(pt[0].d) + '" y="' + (A - 10) + '" text-anchor="start" class="gt">' + NT.fmtData(pt[0].d) + '</text>';
    s += '<text x="' + X(pt[pt.length - 1].d) + '" y="' + (A - 10) + '" text-anchor="end" class="gt">' + NT.fmtData(pt[pt.length - 1].d) + '</text></svg>';
    const diff = pt[pt.length - 1].v - pt[0].v, giorni = NT.giorniTra(pt[0].d, pt[pt.length - 1].d);
    return h('div', { class: 'scheda' }, h('h3', {}, NT.t('Diameter over time')), NT.html(s),
      h('p', { class: 'piccolo' }, NT.t('Change:') + ' ', h('strong', {}, (diff >= 0 ? '+' : '') + NT.num(diff) + ' mm'), ' ' + NT.tp(giorni, 'in {n} day.', 'in {n} days.') + ' ',
        NT.t('These are measurements you entered: they are valid if always taken the same way. A mole that grows or changes is a good reason to show it to your dermatologist; the 6 mm line is just the classic reference of the ABCDE criteria.')),
      h('button', { class: 'btn-testo', onclick: dialogoABCDE }, NT.t('ABCDE reminder')));
  }

  function dialogoABCDE() {
    const voci = [['A', NT.t('Asymmetry'), NT.t('The two halves of the mole do not look alike.')], ['B', NT.t('Border'), NT.t('Irregular, jagged or blurred.')],
      ['C', NT.t('Colour'), NT.t('Several colours in the same mole (brown, black, red, blue, white).')], ['D', NT.t('Diameter'), NT.t('More than 6 mm (but smaller melanomas exist).')],
      ['E', NT.t('Evolution'), NT.t('It changes over time: shape, colour, size, elevation, or itching or bleeding appear.')]];
    NT.apriDialogo(h('div', {}, h('h3', {}, NT.t('ABCDE reminder')),
      h('ul', { class: 'abcde' }, voci.map(([l, t, d]) => h('li', {}, h('b', {}, l), h('span', {}, h('strong', {}, t), ' – ', d)))),
      h('p', { class: 'piccolo' }, NT.t('The «ugly duckling» also counts: a mole that looks different from all the others. Nodules that grow quickly or feel hard to the touch should be shown straight away. This reminder does not replace a medical visit.')),
      h('div', { class: 'azioni' }, h('button', { class: 'btn btn-pri', onclick: () => NT.chiudiDialogo() }, NT.t('Close')))));
  }

  NT.dialogoABCDE = dialogoABCDE;

  /* ---------------------------------- comparison ---------------------------------- */
  function dialogoConfronto(foto, corrente) {
    let a = foto[0], b = foto[foto.length - 1];
    if (corrente && foto.length > 2) { const i = foto.indexOf(corrente); b = corrente; a = i > 0 ? foto[i - 1] : foto[1]; if (a.id === b.id) a = foto[0]; if (new Date(a.scattata_il) > new Date(b.scattata_il)) [a, b] = [b, a]; }
    let sovrapposto = false, posizione = 50;
    const etich = f => NT.fmtData(f.scattata_il) + (f.diametro_mm ? ' · ' + NT.num(f.diametro_mm) + ' mm' : '');
    const selA = h('select', { class: 'campo', onchange: () => { a = foto.find(x => x.id === +selA.value); ridisegna(); } }, foto.map(f => h('option', { value: f.id, selected: f.id === a.id }, etich(f))));
    const selB = h('select', { class: 'campo', onchange: () => { b = foto.find(x => x.id === +selB.value); ridisegna(); } }, foto.map(f => h('option', { value: f.id, selected: f.id === b.id }, etich(f))));
    const area = h('div', { class: 'confronto-area' });
    const modoBtn = h('button', { class: 'btn', onclick: () => { sovrapposto = !sovrapposto; modoBtn.textContent = sovrapposto ? NT.t('Show side by side') : NT.t('Overlay with slider'); ridisegna(); } }, NT.t('Overlay with slider'));
    function ridisegna() {
      const giorni = NT.giorniTra(a.scattata_il, b.scattata_il);
      const dd = (a.diametro_mm && b.diametro_mm) ? ' ' + NT.t('Diameter: {diff} mm difference.', { diff: NT.num(b.diametro_mm - a.diametro_mm) }) : '';
      const nota = h('p', { class: 'piccolo' }, NT.tp(Math.abs(giorni), '{n} day has passed between the two photos.', '{n} days have passed between the two photos.') + dd + ' ' + NT.t('Compare shape, borders and colours: if you notice differences, show the photos to your dermatologist.'));
      if (!sovrapposto) {
        area.replaceChildren(h('div', { class: 'confronto-coppia' },
          h('figure', {}, h('img', { src: '/foto/' + a.id + '/mini?l=960', alt: '' }), h('figcaption', {}, etich(a))),
          h('figure', {}, h('img', { src: '/foto/' + b.id + '/mini?l=960', alt: '' }), h('figcaption', {}, etich(b)))), nota);
      } else {
        const top = h('img', { src: '/foto/' + a.id + '/mini?l=960', alt: '', class: 'sopra', style: { clipPath: 'inset(0 ' + (100 - posizione) + '% 0 0)' } });
        const cur = h('input', { type: 'range', min: 0, max: 100, value: posizione, 'aria-label': NT.t('Comparison slider'), oninput: () => { posizione = +cur.value; top.style.clipPath = 'inset(0 ' + (100 - posizione) + '% 0 0)'; } });
        area.replaceChildren(h('div', { class: 'sovrapposte' }, h('img', { src: '/foto/' + b.id + '/mini?l=960', alt: '' }), top),
          cur, h('div', { class: 'didascalie' }, h('span', {}, '← ' + etich(a)), h('span', {}, etich(b) + ' →')), nota);
      }
    }
    ridisegna();
    NT.apriDialogo(h('div', {}, h('h3', {}, NT.t('Comparison of two photos')),
      h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, NT.t('Before'), selA), h('label', { class: 'etichetta' }, NT.t('After'), selB)),
      modoBtn, area, h('div', { class: 'azioni' }, h('button', { class: 'btn btn-pri', onclick: () => NT.chiudiDialogo() }, NT.t('Close')))), true);
  }

  /* ------------------------------ automatic analysis ------------------------------ */
  async function caricaAnalisi(fotoId) {
    const box = $('#box-analisi');
    if (!box || fotoId !== fotoSel) return;
    let st;
    try { st = await NT.get('/api/foto/' + fotoId + '/analisi'); } catch (e) { box.replaceChildren(h('h3', {}, NT.t('Automatic analysis')), h('p', { class: 'errore-campo' }, e.message)); return; }
    if (fotoId !== fotoSel || !$('#box-analisi')) return;
    const attiva = st.stato === 'in_coda' || st.stato === 'in_corso';
    if (attiva) inAnalisi.add(fotoId);
    else if (inAnalisi.has(fotoId)) {                          // just finished: I update the list and the dots
      inAnalisi.delete(fotoId);
      await ricaricaDettaglio();
      renderPannello();
      return;
    }
    box.replaceChildren(h('h3', {}, NT.t('Automatic analysis')), contenutoAnalisi(fotoId, st));
    if (attiva) pollTimer = setTimeout(() => caricaAnalisi(fotoId), 3000);
  }

  async function avviaAnalisi(fotoId) {
    try { await NT.api('POST', '/api/foto/' + fotoId + '/analizza'); inAnalisi.add(fotoId); caricaAnalisi(fotoId); } catch (e) { NT.errore(e); }
  }

  function contenutoAnalisi(fotoId, st) {
    if (st.stato === 'nessuna') {
      return h('div', {}, h('p', {}, NT.t('This photo has not been analysed yet. The analysis compares several methods on the same image and tells you what each one answered.')),
        h('p', { class: 'piccolo muted' }, NT.t('The first analysis can take several minutes (the models are loaded into memory).') + ' ' +
          (st.skinsense_attivo ? NT.t('SkinSense is on: the photo (without metadata) will be sent to an online service.') : NT.t('The photo stays on your computer: SkinSense (online service) is turned off.'))),
        h('button', { class: 'btn btn-pri', onclick: () => avviaAnalisi(fotoId) }, NT.t('Analyse this photo')));
    }
    if (st.stato === 'in_coda' || st.stato === 'in_corso') {
      return h('div', { class: 'analisi-attesa' }, h('div', { class: 'riga-spinner' }, h('span', { class: 'spinner grande' }),
        h('div', {}, h('strong', {}, st.stato === 'in_coda' ? (st.posizione_coda > 0 ? NT.t('Queued (position {n})…', { n: st.posizione_coda }) : NT.t('Queued…')) : NT.t('Analysis in progress…')),
          h('p', { class: 'piccolo muted' }, NT.t('You can keep using the app. If you close the window the analysis is not lost: the program finishes the work and then shuts down by itself.')))),
        st.avanzamento && st.avanzamento.length ? h('pre', { class: 'log' }, st.avanzamento.join('\n')) : null);
    }
    if (st.stato === 'errore') {
      return h('div', {}, h('p', { class: 'errore-campo' }, st.messaggio ? NT.tr(st.messaggio) : NT.t('The analysis failed.')),
        h('button', { class: 'btn', onclick: () => avviaAnalisi(fotoId) }, NT.t('Try again')));
    }
    return renderSintesi(st.sintesi, fotoId);
  }

  const GIUDIZIO_NESSUNO = NT.t('No method produced a result: check the reasons listed below.');
  const GIUDIZIO_ATT = NT.t('At least one method (or one of its models) flags a lesion that needs attention. This is not a diagnosis and these tools are often wrong, but it is one more reason not to put off the dermatology visit and to bring this report.');
  const GIUDIZIO_BEN = NT.t('None of the methods that responded flags the lesion as suspicious. This does NOT rule out a melanoma: the tools are not clinically validated and are also wrong in this direction. If the mole is asymmetric, has irregular borders, several colours, is larger than 6 mm or has changed over time, a visit is still needed.');
  const AVVERTENZE = [
    NT.t('This report is NOT a diagnosis. The programs used are research prototypes, not medical devices.'),
    NT.t('The methods are trained on photographs different from yours: changing light, distance or camera can change the answer.'),
    NT.t("Phototype, age and family history do not change the neural networks' result (they only look at pixels): they serve to put the risk in context."),
    NT.t('It is normal for the methods to disagree: it only means that none of them is reliable on its own.'),
  ];

  /* Label of a model, like "NEV (naevus, i.e. a benign mole)": the code stays, the description is translated. */
  function etichettaRisultato(testo) {
    const m = /^([A-Z]{3}) \((.+)\)$/.exec(testo || '');
    return m ? m[1] + ' (' + NT.tr(m[2]) + ')' : NT.tr(testo);
  }

  /* "4 of 5: NEV (...); 1 of 5: MEL (...)" - the count of identical results, in the chosen language */
  function fraseConteggio(ok) {
    const conteggi = new Map();
    ok.forEach(r => conteggi.set(r.etichetta, (conteggi.get(r.etichetta) || 0) + 1));
    return [...conteggi.entries()].sort((a, b) => b[1] - a[1])
      .map(([et, n]) => NT.t('{n} of {tot}: {et}', { n: n, tot: ok.length, et: etichettaRisultato(et) })).join('; ');
  }

  function renderSintesi(s, fotoId) {
    const giud = s.con_risultato.length === 0 ? GIUDIZIO_NESSUNO : (s.attenzione.length || s.discordi.length) ? GIUDIZIO_ATT : GIUDIZIO_BEN;
    const schede = s.metodi.map(m => {
      const ok = m.risultati.filter(r => r.stato === 'ok');
      const piu = new Set(m.risultati.map(r => r.gruppo).filter(Boolean)).size > 1;
      return h('div', { class: 'metodo' },
        h('div', { class: 'metodo-testa' }, h('strong', {}, NT.t('Method {n}', { n: m.numero })), h('span', { class: 'metodo-titolo' }, NT.tr(m.titolo)),
          m.verdetto ? NT.chipEsito(m.verdetto) : h('span', { class: 'chip chip-neutro' }, NT.t('No result'))),
        m.introduzione ? h('p', { class: 'piccolo muted' }, NT.tr(m.introduzione)) : null,
        ok.length ? h('p', { class: 'ha-detto' }, NT.t('Method {n} said:', { n: m.numero }) + ' ', h('strong', {}, fraseConteggio(ok))) : null,
        h('ul', { class: 'modelli' }, m.risultati.map(r => r.stato === 'ok'
          ? h('li', {}, h('span', { class: 'mod-nome' }, (piu && r.gruppo ? '[' + NT.tr(r.gruppo) + '] ' : '') + r.nome), h('span', {}, '→ ' + etichettaRisultato(r.etichetta)),
            h('span', { class: 'muted' }, NT.t('confidence {perc}', { perc: NT.perc(r.valore) }) + (r.prob_mel !== null && r.prob_mel !== undefined ? ' · ' + NT.t('melanoma prob. {perc}', { perc: NT.perc(r.prob_mel) }) : '')))
          : h('li', { class: 'nota-metodo ' + r.stato }, h('span', {}, (r.stato === 'errore' ? NT.t('{nome}: error.', { nome: r.nome }) + ' ' : r.stato === 'non_disponibile' ? NT.t('{nome}: not available.', { nome: r.nome }) + ' ' : '') + NT.tr(r.nota || ''))))));
    });
    return h('div', { class: 'sintesi' },
      h('div', { class: 'sintesi-testa' }, NT.chipEsito(s.esito), h('span', { class: 'piccolo muted' }, NT.t('{n} of {tot} methods responded', { n: s.con_risultato.length, tot: s.metodi.length }))),
      h('p', { class: 'giudizio' }, giud),
      schede,
      h('details', { class: 'consigli' }, h('summary', {}, NT.t('Important notices')), h('ul', {}, AVVERTENZE.map(a => h('li', {}, a)))),
      s.testo ? h('details', { class: 'consigli' }, h('summary', {}, NT.lingua === 'en' ? NT.t('Full report (text)') : NT.t('Full report (text, in English)')), h('pre', { class: 'rapporto' }, s.testo)) : null,
      h('button', { class: 'btn-testo', onclick: () => avviaAnalisi(fotoId) }, NT.t('Re-analyse')));
  }
})();
