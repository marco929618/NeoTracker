/* ============================================================================
   v_mappa.js - mappa del corpo, elenco dei nei, storico fotografico e analisi
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h, $ = NT.$;

  const SEDI_UTILI = [NT.m('palmo della mano'), NT.m('dorso della mano'), NT.m('pianta del piede'), NT.m('dorso del piede'), NT.m('spazio tra le dita'),
    NT.m('sotto l\'unghia (mano)'), NT.m('sotto l\'unghia (piede)'), NT.m('cuoio capelluto'), NT.m('orecchio'), NT.m('palpebra'), NT.m('labbro')];
  const GIORNI_PROMEMORIA = 90;

  let mappa = null, modo = 'lista', bozza = null, dett = null, fotoSel = null, pollTimer = null;
  let etichettaRegione = null, panel = null, formFotoAperto = false, sedeBozzaManuale = false;
  const inAnalisi = new Set();

  const nomiAuto = () => new Set(['fronte', 'retro'].flatMap(v => window.Corpo.regioni(v).map(r => r.nome)));
  /* Le sedi della mappa e quelle suggerite si salvano sempre in italiano (così funzionano in tutte le lingue);
     l'utente le vede e le scrive nella sua lingua: qui si torna dal testo tradotto a quello italiano. */
  const sedeCanonica = (() => {
    let inverso = null;
    return testo => {
      const v = String(testo || '').trim();
      if (NT.lingua === 'it') return v;
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
      NT.icona('mirino', 18), NT.t('Aggiungi neo'));
    const suggerimento = h('span', { class: 'mappa-hint', id: 'mappa-hint' }, NT.t('Rotella = zoom · trascina = sposta · doppio clic = ingrandisci'));
    const barra = h('div', { class: 'mappa-barra' }, btnAggiungi, suggerimento,
      h('span', { class: 'spazio' }),
      h('button', { class: 'btn-icona', title: NT.t('Riduci'), onclick: () => mappa.zoomSu(1 / 1.5) }, NT.icona('meno')),
      h('button', { class: 'btn-icona', title: NT.t('Ingrandisci'), onclick: () => mappa.zoomSu(1.5) }, NT.icona('piu')),
      h('button', { class: 'btn-icona', title: NT.t('Mostra tutto il corpo'), onclick: () => mappa.reset() }, NT.icona('reset')));
    const box = h('div', { class: 'mappa-box' });
    etichettaRegione = h('div', { class: 'regione-etichetta' }, NT.t('Passa il puntatore sul corpo per vedere la zona'));
    const legenda = h('div', { class: 'legenda' },
      h('span', {}, h('i', { class: 'pallino pieno' }), NT.t('Neo con foto')),
      h('span', {}, h('i', { class: 'pallino vuoto' }), NT.t('Ancora nessuna foto')),
      h('span', {}, h('i', { class: 'pallino rosso' }), NT.t('Analisi: da attenzionare')),
      h('span', { class: 'lato-nota' }, NT.t('D = destra del paziente · S = sinistra')));
    panel = h('aside', { class: 'pannello', 'aria-live': 'polite' });
    cont.replaceChildren(h('div', { class: 'mappa-layout' }, h('section', { class: 'scheda mappa-scheda' }, barra, box, etichettaRegione, legenda), panel));

    mappa = new window.Corpo.MappaCorpo(box, {
      onRegione: nome => { etichettaRegione.textContent = nome ? NT.tr(nome) : NT.t('Passa il puntatore sul corpo per vedere la zona'); },
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
    if (hint) hint.textContent = on ? NT.t('Clicca sul punto esatto del corpo dove si trova il neo (puoi ingrandire prima)') : NT.t('Rotella = zoom · trascina = sposta · doppio clic = ingrandisci');
    if (on) { aggiornaMarcatori(); renderPannello(); }
  }

  function tornaLista() {
    stopPoll(); modo = 'lista'; dett = null; fotoSel = null; bozza = null;
    if (mappa) { mappa.modalitaAggiunta(false); }
    attivaAggiunta(false);
    aggiornaMarcatori(); renderPannello();
  }

  /* ---------------------------- nuovo neo ---------------------------------- */
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
  const testoPos = p => NT.t('{vista} · posizione {x}% da sinistra, {y}% dall\'alto',
    { vista: p.vista === 'fronte' ? NT.t('Fronte') : NT.t('Retro'), x: Math.round(p.x * 100), y: Math.round(p.y * 100) });

  function pannelloBozza() {
    const nome = h('input', { type: 'text', class: 'campo', maxlength: 60, value: NT.t('Neo {n}', { n: S.nei.length + 1 }), id: 'campo-nome-bozza' });
    const sede = h('input', { type: 'text', class: 'campo', maxlength: 80, list: 'sedi-utili', value: bozza.regione ? NT.tr(bozza.regione) : '', id: 'campo-sede-bozza',
      oninput: () => { sedeBozzaManuale = true; } });
    const note = h('textarea', { class: 'campo', rows: 3, maxlength: 1000, placeholder: NT.t('Quando l\'hai notato, se prude, se è cambiato…') });
    const salva = h('button', { class: 'btn btn-pri', onclick: async () => {
      salva.disabled = true;
      try {
        const r = await NT.api('POST', '/api/utenti/' + S.utente.id + '/nevi',
          { nome: nome.value, vista: bozza.vista, x: bozza.x, y: bozza.y, regione: sedeCanonica(sede.value), note: note.value });
        await NT.ricaricaNei();
        bozza = null; mappa.setBozza(null);
        formFotoAperto = true;
        await selezionaNeo(r.id);
        NT.toast(NT.t('Neo salvato. Ora aggiungi la prima foto: sarà la tua "foto storica".'), 'ok');
      } catch (e) { salva.disabled = false; NT.errore(e); }
    } }, NT.t('Salva neo'));
    return h('div', { class: 'scheda' },
      h('h2', {}, NT.t('Nuovo neo')),
      h('p', { class: 'piccolo', id: 'info-pos-bozza' }, testoPos(bozza)),
      h('p', { class: 'piccolo' }, NT.icona('mirino', 14), ' ' + NT.t('Trascina il pallino sulla mappa per correggere la posizione; ingrandisci con la rotella per la massima precisione.')),
      h('label', { class: 'etichetta' }, NT.t('Nome'), nome),
      h('label', { class: 'etichetta' }, NT.t('Sede (modificabile)'), sede,
        h('datalist', { id: 'sedi-utili' }, opzioniSedi())),
      h('label', { class: 'etichetta' }, NT.t('Note'), note),
      h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => tornaLista() }, NT.t('Annulla')), salva));
  }

  /* ------------------------- spostamento di un neo -------------------------- */
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
      NT.toast(corpo.regione ? NT.t('Posizione aggiornata: {regione}.', { regione: NT.tr(corpo.regione) }) : NT.t('Posizione aggiornata.'), 'ok');
    } catch (e) { NT.errore(e); await NT.ricaricaNei(); aggiornaMarcatori(); }
  }

  /* --------------------------- selezione di un neo -------------------------- */
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

  /* ============================== PANNELLO ================================== */
  function renderPannello() {
    if (!panel) return;
    stopPoll();
    const top = panel.scrollTop;
    panel.replaceChildren(modo === 'bozza' && bozza ? pannelloBozza() : modo === 'neo' && dett ? pannelloNeo() : pannelloLista());
    panel.scrollTop = modo === 'neo' ? top : 0;
    if (modo === 'neo' && fotoSel) caricaAnalisi(fotoSel);
  }

  /* ------------------------------ elenco dei nei ----------------------------- */
  function schedaLista(n) {
    const giorni = n.giorni_da_ultima;
    const promemoria = giorni !== null && giorni >= GIORNI_PROMEMORIA && !n.archiviato;
    return h('button', { class: 'neo-card', onclick: () => selezionaNeo(n.id, true) },
      h('span', { class: 'neo-num' + (n.n_foto === 0 ? ' vuoto' : '') + (n.ultimo_esito === 'attenzione' || n.ultimo_esito === 'discordante' ? ' rosso' : '') }, numDi(n.id)),
      n.ultima_foto_id ? h('img', { class: 'neo-thumb', src: '/foto/' + n.ultima_foto_id + '/mini?l=120', alt: '', loading: 'lazy' }) : h('span', { class: 'neo-thumb vuota' }, NT.icona('foto', 22)),
      h('span', { class: 'neo-info' },
        h('strong', {}, n.nome),
        h('span', { class: 'sotto' }, n.regione ? NT.tr(n.regione) : (n.vista === 'fronte' ? NT.t('Fronte') : NT.t('Retro'))),
        h('span', { class: 'sotto' }, n.n_foto === 0 ? NT.t('Nessuna foto: aggiungi la prima')
          : NT.t('{foto} · ultima {quando}', { foto: NT.tp(n.n_foto, '{n} foto', '{n} foto'), quando: NT.fraseGiorni(giorni) })),
        h('span', { class: 'chips' }, NT.chipEsito(n.ultimo_esito), promemoria ? h('span', { class: 'chip chip-neutro' }, NT.t('Da rifotografare?')) : null)));
  }

  function pannelloLista() {
    const lista = attivi(), arch = S.nei.filter(n => n.archiviato);
    const vuoto = !S.nei.length;
    return h('div', { class: 'scheda' },
      h('div', { class: 'testa-lista' }, h('h2', {}, vuoto ? NT.t('Nessun neo ancora') : NT.t('I tuoi nei ({n})', { n: lista.length })),
        lista.length ? h('button', { class: 'btn-testo', title: NT.t('Stampa una scheda con tutti i nei'), onclick: () => NT.stampaNei(lista.map(n => n.id)) }, NT.icona('stampa', 16), NT.t('Scheda per il dermatologo')) : null),
      vuoto
        ? h('ol', { class: 'passi' },
          h('li', {}, NT.t('Premi'), ' ', h('strong', {}, NT.t('Aggiungi neo')), ' ' + NT.t('e clicca sul punto esatto del corpo (ingrandisci con la rotella per essere più preciso).')),
          h('li', {}, NT.t('Dai un nome al neo e controlla la sede.')),
          h('li', {}, NT.t('Aggiungi la prima foto: diventa la tua foto storica, e ogni foto successiva ne seguirà l\'evoluzione.')))
        : h('div', { class: 'neo-elenco' }, lista.map(schedaLista)),
      arch.length ? h('details', { class: 'archiviati' }, h('summary', {}, NT.t('Nei archiviati ({n})', { n: arch.length })),
        arch.map(n => h('div', { class: 'riga-arch' }, h('span', {}, n.nome + (n.regione ? ' – ' + NT.tr(n.regione) : '')),
          h('button', { class: 'btn-testo', onclick: async () => { try { await NT.api('PATCH', '/api/nevi/' + n.id, { archiviato: false }); await NT.ricaricaNei(); aggiornaMarcatori(); renderPannello(); } catch (e) { NT.errore(e); } } }, NT.t('Ripristina'))))) : null,
      !vuoto ? h('p', { class: 'piccolo muted' }, NT.t('Clicca un neo nell\'elenco o sulla mappa per vedere lo storico fotografico.')) : null);
  }

  /* ------------------------------ dettaglio neo ------------------------------ */
  function pannelloNeo() {
    const n = dett.nevo, foto = dett.foto;
    const salva = async (campi) => { try { await NT.api('PATCH', '/api/nevi/' + n.id, campi); await ricaricaDettaglio(); } catch (e) { NT.errore(e); } };

    const nome = h('input', { type: 'text', class: 'campo titolo-modifica', maxlength: 60, value: n.nome, 'aria-label': NT.t('Nome del neo'),
      onchange: () => { if (nome.value.trim()) salva({ nome: nome.value }); else nome.value = n.nome; } });
    const sede = h('input', { type: 'text', class: 'campo', maxlength: 80, list: 'sedi-utili', value: n.regione ? NT.tr(n.regione) : '', placeholder: NT.t('Sede'),
      onchange: () => salva({ regione: sedeCanonica(sede.value) }) });
    const note = h('textarea', { class: 'campo', rows: 2, maxlength: 1000, placeholder: NT.t('Note sul neo…'), onchange: () => salva({ note: note.value }) }, n.note);

    const testa = h('div', { class: 'scheda' },
      h('div', { class: 'neo-testa' },
        h('button', { class: 'btn-testo', onclick: () => tornaLista() }, NT.t('← Tutti i nei')),
        h('span', { class: 'spazio' }),
        h('button', { class: 'btn-icona', title: NT.t('Centra sulla mappa'), onclick: () => mappa.centraSu(n, 5) }, NT.icona('mirino')),
        h('button', { class: 'btn-icona', title: NT.t('Stampa la scheda di questo neo'), onclick: () => NT.stampaNei([n.id]) }, NT.icona('stampa')),
        h('button', { class: 'btn-icona', title: NT.t('Archivia (toglie dalla mappa, conserva i dati)'), onclick: async () => {
          await salva({ archiviato: true }); tornaLista(); NT.toast(NT.t('Neo archiviato. Lo trovi in fondo all\'elenco.'), 'ok'); } }, NT.icona('archivio')),
        h('button', { class: 'btn-icona pericolo', title: NT.t('Elimina questo neo e le sue foto'), onclick: async () => {
          const si = await NT.conferma(NT.t('Eliminare «{nome}»?', { nome: n.nome }),
            NT.tp(foto.length, 'Verranno cancellate per sempre la sua unica foto e i rapporti di analisi.', 'Verranno cancellate per sempre tutte le sue {n} foto e i rapporti di analisi.'),
            { si: NT.t('Elimina'), pericolo: true, scrivi: foto.length ? n.nome : null });
          if (!si) return;
          try { await NT.api('DELETE', '/api/nevi/' + n.id); await NT.ricaricaNei(); tornaLista(); NT.toast(NT.t('Neo eliminato.'), 'ok'); } catch (e) { NT.errore(e); } } }, NT.icona('cestino'))),
      h('div', { class: 'neo-titolo' }, h('span', { class: 'neo-num grande' + (foto.length ? '' : ' vuoto') }, numDi(n.id)), nome),
      h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, NT.t('Sede'), sede,
        h('datalist', { id: 'sedi-utili' }, opzioniSedi())),
        h('div', { class: 'etichetta' }, NT.t('Posizione'), h('div', { class: 'piccolo' }, testoPos(n), h('br'), NT.t('Trascina il pallino sulla mappa per spostarlo.')))),
      h('label', { class: 'etichetta' }, NT.t('Note'), note));

    const sezioni = [testa, sezioneStorico(n, foto), formFoto(n)];
    const grafico = graficoDiametro(foto);
    if (grafico) sezioni.push(grafico);
    sezioni.push(h('div', { class: 'scheda', id: 'box-analisi' }, h('h3', {}, NT.t('Analisi automatica')), NT.caricamento(NT.t('Controllo lo stato…'))));
    return h('div', { class: 'pila' }, sezioni);
  }

  /* ----------------------------- storico fotografico ----------------------------- */
  function sezioneStorico(n, foto) {
    if (!foto.length) {
      return h('div', { class: 'scheda' }, h('h3', {}, NT.t('Storico fotografico')),
        NT.vuoto(NT.t('Ancora nessuna foto'), NT.t('Aggiungi qui sotto la prima foto: sarà il punto di partenza per vedere se il neo cambia nel tempo.')));
    }
    const f = foto.find(x => x.id === fotoSel) || foto[foto.length - 1];
    const striscia = h('div', { class: 'striscia' }, foto.map(x => h('button', { class: 'miniatura' + (x.id === f.id ? ' sel' : ''), title: NT.fmtData(x.scattata_il) + (x.diametro_mm ? ' · ' + NT.num(x.diametro_mm) + ' mm' : ''),
      onclick: () => { fotoSel = x.id; renderPannello(); } },
      h('img', { src: '/foto/' + x.id + '/mini?l=240', alt: NT.t('Foto del {data}', { data: NT.fmtData(x.scattata_il) }), loading: 'lazy' }),
      h('span', { class: 'data' }, NT.fmtData(x.scattata_il)),
      x.esito && x.esito !== 'nessuno' ? h('i', { class: 'punto-esito ' + NT.ESITI[x.esito].cls, title: NT.ESITI[x.esito].testo }) : null)));
    const precedente = foto[foto.indexOf(f) - 1];
    const meta = h('div', { class: 'foto-meta' },
      h('span', {}, h('strong', {}, NT.fmtData(f.scattata_il)), ' · ', f.tipo === 'dermoscopica' ? NT.t('dermoscopica') : NT.t('foto normale')),
      f.diametro_mm ? h('span', {}, NT.t('Diametro:') + ' ', h('strong', {}, NT.num(f.diametro_mm) + ' mm'),
        precedente && precedente.diametro_mm ? h('span', { class: 'delta' }, ' ' + NT.t('({variazione} mm dalla foto precedente)', { variazione: (f.diametro_mm - precedente.diametro_mm >= 0 ? '+' : '') + NT.num(f.diametro_mm - precedente.diametro_mm) })) : null) : null,
      f.note ? h('span', { class: 'muted' }, f.note) : null);
    return h('div', { class: 'scheda' },
      h('div', { class: 'testa-lista' }, h('h3', {}, NT.t('Storico fotografico ({n})', { n: foto.length })),
        foto.length >= 2 ? h('button', { class: 'btn-testo', onclick: () => dialogoConfronto(foto, f) }, NT.icona('confronta', 16), NT.t('Confronta')) : null),
      striscia,
      h('button', { class: 'anteprima', title: NT.t('Clic per vedere la foto originale a schermo intero'), onclick: () => apriLightbox(f) },
        h('img', { src: '/foto/' + f.id + '/mini?l=960', alt: NT.t('Foto del {data}', { data: NT.fmtData(f.scattata_il) }) })),
      meta,
      h('div', { class: 'azioni-foto' },
        h('button', { class: 'btn-testo', onclick: () => dialogoModificaFoto(f) }, NT.t('Modifica data/misura')),
        h('button', { class: 'btn-testo pericolo', onclick: async () => {
          const si = await NT.conferma(NT.t('Eliminare questa foto?'), NT.t('La foto del {data} e il suo rapporto di analisi saranno cancellati per sempre.', { data: NT.fmtData(f.scattata_il) }), { si: NT.t('Elimina foto'), pericolo: true });
          if (!si) return;
          try { await NT.api('DELETE', '/api/foto/' + f.id); await ricaricaDettaglio(); fotoSel = dett.foto.length ? dett.foto[dett.foto.length - 1].id : null; renderPannello(); NT.toast(NT.t('Foto eliminata.'), 'ok'); } catch (e) { NT.errore(e); } } }, NT.t('Elimina foto'))));
  }

  function apriLightbox(f) {
    const d = $('#lightbox');
    d.replaceChildren(h('div', { class: 'lb' },
      h('div', { class: 'lb-barra' }, h('strong', {}, NT.fmtData(f.scattata_il)), h('span', { class: 'spazio' }), h('button', { class: 'btn', onclick: () => d.close() }, NT.t('Chiudi'))),
      h('img', { src: '/foto/' + f.id + '/originale', alt: NT.t('Foto originale') })));
    d.showModal();
  }

  function dialogoModificaFoto(f) {
    const data = h('input', { type: 'date', class: 'campo', value: f.scattata_il, max: NT.oggiISO() });
    const diam = h('input', { type: 'text', class: 'campo', inputmode: 'decimal', value: f.diametro_mm === null ? '' : NT.num(f.diametro_mm), placeholder: NT.t('es. 4,5') });
    const tipo = h('select', { class: 'campo' }, h('option', { value: 'normale', selected: f.tipo === 'normale' }, NT.t('Foto normale')), h('option', { value: 'dermoscopica', selected: f.tipo === 'dermoscopica' }, NT.t('Dermoscopica')));
    const nota = h('textarea', { class: 'campo', rows: 2, maxlength: 1000 }, f.note);
    NT.apriDialogo(h('div', {}, h('h3', {}, NT.t('Modifica foto')),
      h('label', { class: 'etichetta' }, NT.t('Data dello scatto'), data), h('label', { class: 'etichetta' }, NT.t('Diametro (mm)'), diam),
      h('label', { class: 'etichetta' }, NT.t('Tipo'), tipo), h('label', { class: 'etichetta' }, NT.t('Note'), nota),
      h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => NT.chiudiDialogo() }, NT.t('Annulla')),
        h('button', { class: 'btn btn-pri', onclick: async () => {
          try {
            await NT.api('PATCH', '/api/foto/' + f.id, { scattata_il: data.value, diametro_mm: diam.value, tipo: tipo.value, note: nota.value });
            NT.chiudiDialogo(); await ricaricaDettaglio(); renderPannello();
          } catch (e) { NT.errore(e); }
        } }, NT.t('Salva')))));
  }

  /* ----------------------------- aggiunta di una foto ----------------------------- */
  function formFoto(n) {
    let file = null;
    const anteprima = h('div', { class: 'drop-testo' }, NT.icona('foto', 26), h('span', {}, NT.t('Trascina qui una foto oppure clicca per sceglierla')), h('small', {}, NT.t('JPG, PNG, WEBP o BMP · fino a 60 MB')));
    const input = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/bmp,.jpg,.jpeg,.png,.webp,.bmp', class: 'nascosto' });
    const drop = h('label', { class: 'drop' }, input, anteprima);
    const data = h('input', { type: 'date', class: 'campo', value: NT.oggiISO(), max: NT.oggiISO(), oninput: () => { usaExif.checked = false; } });
    const usaExif = h('input', { type: 'checkbox', checked: true });
    const tipo = h('select', { class: 'campo' }, h('option', { value: 'normale' }, NT.t('Foto normale (smartphone)')), h('option', { value: 'dermoscopica' }, NT.t('Dermoscopica')));
    const diam = h('input', { type: 'text', class: 'campo', inputmode: 'decimal', placeholder: NT.t('es. 4,5') });
    const nota = h('input', { type: 'text', class: 'campo', maxlength: 1000, placeholder: NT.t('Facoltativa') });
    const analizza = h('input', { type: 'checkbox', checked: true });
    const btn = h('button', { class: 'btn btn-pri', disabled: true }, NT.icona('foto', 18), NT.t('Salva foto'));

    function scegli(fl) {
      if (!fl) return;
      if (!/^image\//.test(fl.type) && !/\.(jpe?g|png|webp|bmp)$/i.test(fl.name)) { NT.toast(NT.t('Scegli un file immagine (JPG, PNG, WEBP o BMP).'), 'errore'); return; }
      if (fl.size > (S.stato.max_mb_foto || 60) * 1048576) { NT.toast(NT.t('La foto supera i {mb} MB: riducila o scegline un\'altra.', { mb: S.stato.max_mb_foto || 60 }), 'errore'); return; }
      file = fl;
      data.value = NT.dataDaMs(fl.lastModified); usaExif.checked = true;
      const url = URL.createObjectURL(fl);
      anteprima.replaceChildren(h('img', { src: url, alt: NT.t('Anteprima'), class: 'drop-img' }), h('small', {}, NT.t('{nome} · {mb} MB · clicca per cambiare', { nome: fl.name, mb: NT.num(fl.size / 1048576) })));
      btn.disabled = false;
    }
    input.addEventListener('change', () => scegli(input.files[0]));
    ['dragenter', 'dragover'].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.add('sopra'); }));
    ['dragleave', 'drop'].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.remove('sopra'); }));
    drop.addEventListener('drop', ev => scegli(ev.dataTransfer.files[0]));

    btn.addEventListener('click', async () => {
      if (!file) return;
      btn.disabled = true; btn.replaceChildren(h('span', { class: 'spinner' }), NT.t('Salvataggio…'));
      const q = new URLSearchParams({ data: data.value, exif: usaExif.checked ? '1' : '0', tipo: tipo.value, diametro: diam.value, note: nota.value, analizza: analizza.checked ? '1' : '0' });
      try {
        const r = await NT.api('POST', '/api/nevi/' + n.id + '/foto?' + q.toString(), null, { raw: file, tipo: file.type || 'application/octet-stream' });
        formFotoAperto = false;
        await ricaricaDettaglio();
        fotoSel = r.id;
        renderPannello();
        NT.toast((r.da_exif ? NT.t('Foto salvata ({data}, data letta dalla foto).', { data: NT.fmtData(r.scattata_il) }) : NT.t('Foto salvata ({data}).', { data: NT.fmtData(r.scattata_il) }))
          + (r.analisi_errore ? ' ' + NT.tr(r.analisi_errore) : ''), r.analisi_errore ? 'errore' : 'ok');
      } catch (e) { btn.disabled = false; btn.replaceChildren(NT.icona('foto', 18), NT.t('Salva foto')); NT.errore(e); }
    });

    const det = h('details', { class: 'scheda form-foto', open: formFotoAperto || dett.foto.length === 0 },
      h('summary', {}, NT.icona('piu', 16), NT.t('Aggiungi una foto allo storico')),
      h('div', { class: 'form-corpo' }, drop,
        h('div', { class: 'riga-2' },
          h('label', { class: 'etichetta' }, NT.t('Data dello scatto'), data,
            h('span', { class: 'spunta' }, usaExif, ' ' + NT.t('Usa la data scritta nella foto, se c\'è'))),
          h('label', { class: 'etichetta' }, NT.t('Diametro misurato (mm)'), diam)),
        h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, NT.t('Tipo di foto'), tipo), h('label', { class: 'etichetta' }, NT.t('Note'), nota)),
        h('label', { class: 'spunta grande' }, analizza, ' ' + NT.t('Analizza subito con tutti i metodi installati')),
        h('details', { class: 'consigli' }, h('summary', {}, NT.t('Come scattare foto confrontabili')),
          h('ul', {}, h('li', {}, NT.t('Stessa luce (luce del giorno, senza flash) e stessa distanza ogni volta, circa 10-15 cm.')),
            h('li', {}, NT.t('Metti accanto al neo un righello o una moneta: serve per misurare il diametro.')),
            h('li', {}, NT.t('Foto a fuoco, con il neo al centro e la pelle ben visibile (sposta i peli, se serve).')),
            h('li', {}, NT.t('Scatta sempre dalla stessa angolazione e salva l\'originale, senza filtri.')))),
        btn));
    return det;
  }

  /* ------------------------------ grafico del diametro ------------------------------ */
  function graficoDiametro(foto) {
    const pt = foto.filter(f => f.diametro_mm !== null && f.diametro_mm !== undefined).map(f => ({ d: f.scattata_il, v: f.diametro_mm }));
    if (pt.length < 2) return null;
    const L = 380, A = 190, ml = 36, mr = 14, mt = 14, mb = 32;
    const t0 = new Date(pt[0].d + 'T12:00:00').getTime(), t1 = new Date(pt[pt.length - 1].d + 'T12:00:00').getTime();
    const vmax = Math.max(7, Math.ceil(Math.max(...pt.map(p => p.v)) + 1));
    const X = d => ml + (t1 === t0 ? (L - ml - mr) / 2 : (new Date(d + 'T12:00:00').getTime() - t0) / (t1 - t0) * (L - ml - mr));
    const Y = v => A - mb - v / vmax * (A - mb - mt);
    const passo = vmax <= 10 ? 2 : 5;
    let s = '<svg viewBox="0 0 ' + L + ' ' + A + '" class="grafico" role="img" aria-label="' + NT.esc(NT.t('Diametro del neo nel tempo')) + '">';
    for (let v = 0; v <= vmax; v += passo) s += '<line x1="' + ml + '" x2="' + (L - mr) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" class="gl"/><text x="' + (ml - 6) + '" y="' + (Y(v) + 4) + '" text-anchor="end" class="gt">' + v + '</text>';
    s += '<line x1="' + ml + '" x2="' + (L - mr) + '" y1="' + Y(6) + '" y2="' + Y(6) + '" class="g6"/><text x="' + (L - mr) + '" y="' + (Y(6) - 4) + '" text-anchor="end" class="gt g6t">6 mm</text>';
    s += '<polyline class="gline" points="' + pt.map(p => X(p.d) + ',' + Y(p.v)).join(' ') + '"/>';
    pt.forEach(p => { s += '<circle cx="' + X(p.d) + '" cy="' + Y(p.v) + '" r="4.5" class="gp"><title>' + NT.fmtData(p.d) + ': ' + NT.num(p.v) + ' mm</title></circle>'; });
    s += '<text x="' + X(pt[0].d) + '" y="' + (A - 10) + '" text-anchor="start" class="gt">' + NT.fmtData(pt[0].d) + '</text>';
    s += '<text x="' + X(pt[pt.length - 1].d) + '" y="' + (A - 10) + '" text-anchor="end" class="gt">' + NT.fmtData(pt[pt.length - 1].d) + '</text></svg>';
    const diff = pt[pt.length - 1].v - pt[0].v, giorni = NT.giorniTra(pt[0].d, pt[pt.length - 1].d);
    return h('div', { class: 'scheda' }, h('h3', {}, NT.t('Diametro nel tempo')), NT.html(s),
      h('p', { class: 'piccolo' }, NT.t('Variazione:') + ' ', h('strong', {}, (diff >= 0 ? '+' : '') + NT.num(diff) + ' mm'), ' ' + NT.tp(giorni, 'in {n} giorno.', 'in {n} giorni.') + ' ',
        NT.t('Sono misure inserite da te: valgono se prese sempre allo stesso modo. Un neo che cresce o cambia è un buon motivo per farlo vedere al dermatologo; la linea a 6 mm è solo il riferimento classico dei criteri ABCDE.')),
      h('button', { class: 'btn-testo', onclick: dialogoABCDE }, NT.t('Promemoria ABCDE')));
  }

  function dialogoABCDE() {
    const voci = [['A', NT.t('Asimmetria'), NT.t('Le due metà del neo non si somigliano.')], ['B', NT.t('Bordi'), NT.t('Irregolari, frastagliati o sfumati.')],
      ['C', NT.t('Colore'), NT.t('Più colori nello stesso neo (marrone, nero, rosso, blu, bianco).')], ['D', NT.t('Diametro'), NT.t('Più di 6 mm (ma esistono melanomi più piccoli).')],
      ['E', NT.t('Evoluzione'), NT.t('Cambia nel tempo: forma, colore, dimensione, rilievo, o compaiono prurito o sanguinamento.')]];
    NT.apriDialogo(h('div', {}, h('h3', {}, NT.t('Promemoria ABCDE')),
      h('ul', { class: 'abcde' }, voci.map(([l, t, d]) => h('li', {}, h('b', {}, l), h('span', {}, h('strong', {}, t), ' – ', d)))),
      h('p', { class: 'piccolo' }, NT.t('Conta anche il «brutto anatroccolo»: un neo diverso da tutti gli altri. I noduli che crescono rapidamente o sono duri al tatto vanno mostrati subito. Questo promemoria non sostituisce la visita.')),
      h('div', { class: 'azioni' }, h('button', { class: 'btn btn-pri', onclick: () => NT.chiudiDialogo() }, NT.t('Chiudi')))));
  }

  NT.dialogoABCDE = dialogoABCDE;

  /* ---------------------------------- confronto ---------------------------------- */
  function dialogoConfronto(foto, corrente) {
    let a = foto[0], b = foto[foto.length - 1];
    if (corrente && foto.length > 2) { const i = foto.indexOf(corrente); b = corrente; a = i > 0 ? foto[i - 1] : foto[1]; if (a.id === b.id) a = foto[0]; if (new Date(a.scattata_il) > new Date(b.scattata_il)) [a, b] = [b, a]; }
    let sovrapposto = false, posizione = 50;
    const etich = f => NT.fmtData(f.scattata_il) + (f.diametro_mm ? ' · ' + NT.num(f.diametro_mm) + ' mm' : '');
    const selA = h('select', { class: 'campo', onchange: () => { a = foto.find(x => x.id === +selA.value); ridisegna(); } }, foto.map(f => h('option', { value: f.id, selected: f.id === a.id }, etich(f))));
    const selB = h('select', { class: 'campo', onchange: () => { b = foto.find(x => x.id === +selB.value); ridisegna(); } }, foto.map(f => h('option', { value: f.id, selected: f.id === b.id }, etich(f))));
    const area = h('div', { class: 'confronto-area' });
    const modoBtn = h('button', { class: 'btn', onclick: () => { sovrapposto = !sovrapposto; modoBtn.textContent = sovrapposto ? NT.t('Mostra affiancate') : NT.t('Sovrapponi con cursore'); ridisegna(); } }, NT.t('Sovrapponi con cursore'));
    function ridisegna() {
      const giorni = NT.giorniTra(a.scattata_il, b.scattata_il);
      const dd = (a.diametro_mm && b.diametro_mm) ? ' ' + NT.t('Diametro: {diff} mm di differenza.', { diff: NT.num(b.diametro_mm - a.diametro_mm) }) : '';
      const nota = h('p', { class: 'piccolo' }, NT.tp(Math.abs(giorni), 'Tra le due foto è passato {n} giorno.', 'Tra le due foto sono passati {n} giorni.') + dd + ' ' + NT.t('Confronta forma, bordi e colori: se noti differenze, mostra le foto al dermatologo.'));
      if (!sovrapposto) {
        area.replaceChildren(h('div', { class: 'confronto-coppia' },
          h('figure', {}, h('img', { src: '/foto/' + a.id + '/mini?l=960', alt: '' }), h('figcaption', {}, etich(a))),
          h('figure', {}, h('img', { src: '/foto/' + b.id + '/mini?l=960', alt: '' }), h('figcaption', {}, etich(b)))), nota);
      } else {
        const top = h('img', { src: '/foto/' + a.id + '/mini?l=960', alt: '', class: 'sopra', style: { clipPath: 'inset(0 ' + (100 - posizione) + '% 0 0)' } });
        const cur = h('input', { type: 'range', min: 0, max: 100, value: posizione, 'aria-label': NT.t('Cursore di confronto'), oninput: () => { posizione = +cur.value; top.style.clipPath = 'inset(0 ' + (100 - posizione) + '% 0 0)'; } });
        area.replaceChildren(h('div', { class: 'sovrapposte' }, h('img', { src: '/foto/' + b.id + '/mini?l=960', alt: '' }), top),
          cur, h('div', { class: 'didascalie' }, h('span', {}, '← ' + etich(a)), h('span', {}, etich(b) + ' →')), nota);
      }
    }
    ridisegna();
    NT.apriDialogo(h('div', {}, h('h3', {}, NT.t('Confronto tra due foto')),
      h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, NT.t('Prima'), selA), h('label', { class: 'etichetta' }, NT.t('Dopo'), selB)),
      modoBtn, area, h('div', { class: 'azioni' }, h('button', { class: 'btn btn-pri', onclick: () => NT.chiudiDialogo() }, NT.t('Chiudi')))), true);
  }

  /* ------------------------------ analisi automatica ------------------------------ */
  async function caricaAnalisi(fotoId) {
    const box = $('#box-analisi');
    if (!box || fotoId !== fotoSel) return;
    let st;
    try { st = await NT.get('/api/foto/' + fotoId + '/analisi'); } catch (e) { box.replaceChildren(h('h3', {}, NT.t('Analisi automatica')), h('p', { class: 'errore-campo' }, e.message)); return; }
    if (fotoId !== fotoSel || !$('#box-analisi')) return;
    const attiva = st.stato === 'in_coda' || st.stato === 'in_corso';
    if (attiva) inAnalisi.add(fotoId);
    else if (inAnalisi.has(fotoId)) {                          // appena finita: aggiorno elenco e pallini
      inAnalisi.delete(fotoId);
      await ricaricaDettaglio();
      renderPannello();
      return;
    }
    box.replaceChildren(h('h3', {}, NT.t('Analisi automatica')), contenutoAnalisi(fotoId, st));
    if (attiva) pollTimer = setTimeout(() => caricaAnalisi(fotoId), 3000);
  }

  async function avviaAnalisi(fotoId) {
    try { await NT.api('POST', '/api/foto/' + fotoId + '/analizza'); inAnalisi.add(fotoId); caricaAnalisi(fotoId); } catch (e) { NT.errore(e); }
  }

  function contenutoAnalisi(fotoId, st) {
    if (st.stato === 'nessuna') {
      return h('div', {}, h('p', {}, NT.t('Questa foto non è ancora stata analizzata. L\'analisi confronta più metodi sulla stessa immagine e ti dice cosa ha risposto ciascuno.')),
        h('p', { class: 'piccolo muted' }, NT.t('La prima analisi può richiedere diversi minuti (i modelli vengono caricati in memoria).') + ' ' +
          (st.skinsense_attivo ? NT.t('SkinSense è attivo: la foto (senza metadati) verrà inviata a un servizio online.') : NT.t('La foto resta sul tuo computer: SkinSense (servizio online) è disattivato.'))),
        h('button', { class: 'btn btn-pri', onclick: () => avviaAnalisi(fotoId) }, NT.t('Analizza questa foto')));
    }
    if (st.stato === 'in_coda' || st.stato === 'in_corso') {
      return h('div', { class: 'analisi-attesa' }, h('div', { class: 'riga-spinner' }, h('span', { class: 'spinner grande' }),
        h('div', {}, h('strong', {}, st.stato === 'in_coda' ? (st.posizione_coda > 0 ? NT.t('In coda (posizione {n})…', { n: st.posizione_coda }) : NT.t('In coda…')) : NT.t('Analisi in corso…')),
          h('p', { class: 'piccolo muted' }, NT.t('Puoi continuare a usare l\'app. Se chiudi la finestra l\'analisi non va persa: il programma finisce il lavoro e poi si spegne da solo.')))),
        st.avanzamento && st.avanzamento.length ? h('pre', { class: 'log' }, st.avanzamento.join('\n')) : null);
    }
    if (st.stato === 'errore') {
      return h('div', {}, h('p', { class: 'errore-campo' }, st.messaggio ? NT.tr(st.messaggio) : NT.t('L\'analisi non è riuscita.')),
        h('button', { class: 'btn', onclick: () => avviaAnalisi(fotoId) }, NT.t('Riprova')));
    }
    return renderSintesi(st.sintesi, fotoId);
  }

  const GIUDIZIO_NESSUNO = NT.t('Nessun metodo ha prodotto un risultato: controlla i motivi indicati sotto.');
  const GIUDIZIO_ATT = NT.t('Almeno un metodo (o un suo modello) segnala una lesione da attenzionare. Non è una diagnosi e questi strumenti sbagliano spesso, ma è un motivo in più per non rimandare la visita dermatologica e per portare questo rapporto.');
  const GIUDIZIO_BEN = NT.t('Nessuno dei metodi che hanno risposto segnala la lesione come sospetta. Questo NON esclude un melanoma: gli strumenti non sono validati clinicamente e sbagliano anche in questa direzione. Se il neo è asimmetrico, ha bordi irregolari, colori diversi, è più grande di 6 mm o è cambiato nel tempo, la visita resta necessaria.');
  const AVVERTENZE = [
    NT.t('Questo rapporto NON è una diagnosi. I programmi usati sono prototipi di ricerca, non dispositivi medici.'),
    NT.t('I metodi sono addestrati su fotografie diverse dalle tue: cambiare luce, distanza o fotocamera può cambiare la risposta.'),
    NT.t('Fototipo, età e familiarità non cambiano il risultato delle reti neurali (guardano solo i pixel): servono a contestualizzare il rischio.'),
    NT.t('Se i metodi sono in disaccordo è normale: significa solo che nessuno di loro è affidabile da solo.'),
  ];

  /* Etichetta di un modello, come "NEV (nevo, cioe' neo benigno)": il codice resta, la descrizione si traduce. */
  function etichettaRisultato(testo) {
    const m = /^([A-Z]{3}) \((.+)\)$/.exec(testo || '');
    return m ? m[1] + ' (' + NT.tr(m[2]) + ')' : NT.tr(testo);
  }

  /* "4 su 5: NEV (...); 1 su 5: MEL (...)" - il conteggio dei risultati uguali, nella lingua scelta */
  function fraseConteggio(ok) {
    const conteggi = new Map();
    ok.forEach(r => conteggi.set(r.etichetta, (conteggi.get(r.etichetta) || 0) + 1));
    return [...conteggi.entries()].sort((a, b) => b[1] - a[1])
      .map(([et, n]) => NT.t('{n} su {tot}: {et}', { n: n, tot: ok.length, et: etichettaRisultato(et) })).join('; ');
  }

  function renderSintesi(s, fotoId) {
    const giud = s.con_risultato.length === 0 ? GIUDIZIO_NESSUNO : (s.attenzione.length || s.discordi.length) ? GIUDIZIO_ATT : GIUDIZIO_BEN;
    const schede = s.metodi.map(m => {
      const ok = m.risultati.filter(r => r.stato === 'ok');
      const piu = new Set(m.risultati.map(r => r.gruppo).filter(Boolean)).size > 1;
      return h('div', { class: 'metodo' },
        h('div', { class: 'metodo-testa' }, h('strong', {}, NT.t('Metodo {n}', { n: m.numero })), h('span', { class: 'metodo-titolo' }, NT.tr(m.titolo)),
          m.verdetto ? NT.chipEsito(m.verdetto) : h('span', { class: 'chip chip-neutro' }, NT.t('Nessun risultato'))),
        m.introduzione ? h('p', { class: 'piccolo muted' }, NT.tr(m.introduzione)) : null,
        ok.length ? h('p', { class: 'ha-detto' }, NT.t('Il metodo {n} ha detto che:', { n: m.numero }) + ' ', h('strong', {}, fraseConteggio(ok))) : null,
        h('ul', { class: 'modelli' }, m.risultati.map(r => r.stato === 'ok'
          ? h('li', {}, h('span', { class: 'mod-nome' }, (piu && r.gruppo ? '[' + NT.tr(r.gruppo) + '] ' : '') + r.nome), h('span', {}, '→ ' + etichettaRisultato(r.etichetta)),
            h('span', { class: 'muted' }, NT.t('sicurezza {perc}', { perc: NT.perc(r.valore) }) + (r.prob_mel !== null && r.prob_mel !== undefined ? ' · ' + NT.t('prob. melanoma {perc}', { perc: NT.perc(r.prob_mel) }) : '')))
          : h('li', { class: 'nota-metodo ' + r.stato }, h('span', {}, (r.stato === 'errore' ? NT.t('{nome}: errore.', { nome: r.nome }) + ' ' : r.stato === 'non_disponibile' ? NT.t('{nome}: non disponibile.', { nome: r.nome }) + ' ' : '') + NT.tr(r.nota || ''))))));
    });
    return h('div', { class: 'sintesi' },
      h('div', { class: 'sintesi-testa' }, NT.chipEsito(s.esito), h('span', { class: 'piccolo muted' }, NT.t('{n} metodi su {tot} hanno risposto', { n: s.con_risultato.length, tot: s.metodi.length }))),
      h('p', { class: 'giudizio' }, giud),
      schede,
      h('details', { class: 'consigli' }, h('summary', {}, NT.t('Avvertenze')), h('ul', {}, AVVERTENZE.map(a => h('li', {}, a)))),
      s.testo ? h('details', { class: 'consigli' }, h('summary', {}, NT.lingua === 'it' ? NT.t('Rapporto completo (testo)') : NT.t('Rapporto completo (testo, in italiano)')), h('pre', { class: 'rapporto' }, s.testo)) : null,
      h('button', { class: 'btn-testo', onclick: () => avviaAnalisi(fotoId) }, NT.t('Rianalizza')));
  }
})();
