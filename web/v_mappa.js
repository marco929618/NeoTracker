/* ============================================================================
   v_mappa.js - mappa del corpo, elenco dei nei, storico fotografico e analisi
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h, $ = NT.$;

  const SEDI_UTILI = ['palmo della mano', 'dorso della mano', 'pianta del piede', 'dorso del piede', 'spazio tra le dita',
    'sotto l\'unghia (mano)', 'sotto l\'unghia (piede)', 'cuoio capelluto', 'orecchio', 'palpebra', 'labbro'];
  const GIORNI_PROMEMORIA = 90;

  let mappa = null, modo = 'lista', bozza = null, dett = null, fotoSel = null, pollTimer = null;
  let etichettaRegione = null, panel = null, formFotoAperto = false, sedeBozzaManuale = false;
  const inAnalisi = new Set();

  const nomiAuto = () => new Set(['fronte', 'retro'].flatMap(v => window.Corpo.regioni(v).map(r => r.nome)));
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
      NT.icona('mirino', 18), 'Aggiungi neo');
    const suggerimento = h('span', { class: 'mappa-hint', id: 'mappa-hint' }, 'Rotella = zoom · trascina = sposta · doppio clic = ingrandisci');
    const barra = h('div', { class: 'mappa-barra' }, btnAggiungi, suggerimento,
      h('span', { class: 'spazio' }),
      h('button', { class: 'btn-icona', title: 'Riduci', onclick: () => mappa.zoomSu(1 / 1.5) }, NT.icona('meno')),
      h('button', { class: 'btn-icona', title: 'Ingrandisci', onclick: () => mappa.zoomSu(1.5) }, NT.icona('piu')),
      h('button', { class: 'btn-icona', title: 'Mostra tutto il corpo', onclick: () => mappa.reset() }, NT.icona('reset')));
    const box = h('div', { class: 'mappa-box' });
    etichettaRegione = h('div', { class: 'regione-etichetta' }, 'Passa il puntatore sul corpo per vedere la zona');
    const legenda = h('div', { class: 'legenda' },
      h('span', {}, h('i', { class: 'pallino pieno' }), 'Neo con foto'),
      h('span', {}, h('i', { class: 'pallino vuoto' }), 'Ancora nessuna foto'),
      h('span', {}, h('i', { class: 'pallino rosso' }), 'Analisi: da attenzionare'),
      h('span', { class: 'lato-nota' }, 'D = destra del paziente · S = sinistra'));
    panel = h('aside', { class: 'pannello', 'aria-live': 'polite' });
    cont.replaceChildren(h('div', { class: 'mappa-layout' }, h('section', { class: 'scheda mappa-scheda' }, barra, box, etichettaRegione, legenda), panel));

    mappa = new window.Corpo.MappaCorpo(box, {
      onRegione: nome => { etichettaRegione.textContent = nome || 'Passa il puntatore sul corpo per vedere la zona'; },
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
    if (hint) hint.textContent = on ? 'Clicca sul punto esatto del corpo dove si trova il neo (puoi ingrandire prima)' : 'Rotella = zoom · trascina = sposta · doppio clic = ingrandisci';
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
    if (c && bozza) c.value = bozza.regione || '';
    const info = $('#info-pos-bozza');
    if (info && bozza) info.textContent = testoPos(bozza);
  }
  const testoPos = p => (p.vista === 'fronte' ? 'Fronte' : 'Retro') + ' · posizione ' + Math.round(p.x * 100) + '% da sinistra, ' + Math.round(p.y * 100) + '% dall\'alto';

  function pannelloBozza() {
    const nome = h('input', { type: 'text', class: 'campo', maxlength: 60, value: 'Neo ' + (S.nei.length + 1), id: 'campo-nome-bozza' });
    const sede = h('input', { type: 'text', class: 'campo', maxlength: 80, list: 'sedi-utili', value: bozza.regione || '', id: 'campo-sede-bozza',
      oninput: () => { sedeBozzaManuale = true; } });
    const note = h('textarea', { class: 'campo', rows: 3, maxlength: 1000, placeholder: 'Quando l\'hai notato, se prude, se è cambiato…' });
    const salva = h('button', { class: 'btn btn-pri', onclick: async () => {
      salva.disabled = true;
      try {
        const r = await NT.api('POST', '/api/utenti/' + S.utente.id + '/nevi',
          { nome: nome.value, vista: bozza.vista, x: bozza.x, y: bozza.y, regione: sede.value, note: note.value });
        await NT.ricaricaNei();
        bozza = null; mappa.setBozza(null);
        formFotoAperto = true;
        await selezionaNeo(r.id);
        NT.toast('Neo salvato. Ora aggiungi la prima foto: sarà la tua "foto storica".', 'ok');
      } catch (e) { salva.disabled = false; NT.errore(e); }
    } }, 'Salva neo');
    return h('div', { class: 'scheda' },
      h('h2', {}, 'Nuovo neo'),
      h('p', { class: 'piccolo', id: 'info-pos-bozza' }, testoPos(bozza)),
      h('p', { class: 'piccolo' }, NT.icona('mirino', 14), ' Trascina il pallino sulla mappa per correggere la posizione; ingrandisci con la rotella per la massima precisione.'),
      h('label', { class: 'etichetta' }, 'Nome', nome),
      h('label', { class: 'etichetta' }, 'Sede (modificabile)', sede,
        h('datalist', { id: 'sedi-utili' }, SEDI_UTILI.map(s => h('option', { value: s })))),
      h('label', { class: 'etichetta' }, 'Note', note),
      h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => tornaLista() }, 'Annulla'), salva));
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
      NT.toast('Posizione aggiornata' + (corpo.regione ? ': ' + corpo.regione : '') + '.', 'ok');
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
        h('span', { class: 'sotto' }, n.regione || (n.vista === 'fronte' ? 'Fronte' : 'Retro')),
        h('span', { class: 'sotto' }, n.n_foto === 0 ? 'Nessuna foto: aggiungi la prima'
          : n.n_foto + (n.n_foto === 1 ? ' foto' : ' foto') + ' · ultima ' + NT.fraseGiorni(giorni)),
        h('span', { class: 'chips' }, NT.chipEsito(n.ultimo_esito), promemoria ? h('span', { class: 'chip chip-neutro' }, 'Da rifotografare?') : null)));
  }

  function pannelloLista() {
    const lista = attivi(), arch = S.nei.filter(n => n.archiviato);
    const vuoto = !S.nei.length;
    return h('div', { class: 'scheda' },
      h('div', { class: 'testa-lista' }, h('h2', {}, vuoto ? 'Nessun neo ancora' : 'I tuoi nei (' + lista.length + ')'),
        lista.length ? h('button', { class: 'btn-testo', title: 'Stampa una scheda con tutti i nei', onclick: () => NT.stampaNei(lista.map(n => n.id)) }, NT.icona('stampa', 16), 'Scheda per il dermatologo') : null),
      vuoto
        ? h('ol', { class: 'passi' },
          h('li', {}, 'Premi ', h('strong', {}, 'Aggiungi neo'), ' e clicca sul punto esatto del corpo (ingrandisci con la rotella per essere più preciso).'),
          h('li', {}, 'Dai un nome al neo e controlla la sede.'),
          h('li', {}, 'Aggiungi la prima foto: diventa la tua foto storica, e ogni foto successiva ne seguirà l\'evoluzione.'))
        : h('div', { class: 'neo-elenco' }, lista.map(schedaLista)),
      arch.length ? h('details', { class: 'archiviati' }, h('summary', {}, 'Nei archiviati (' + arch.length + ')'),
        arch.map(n => h('div', { class: 'riga-arch' }, h('span', {}, n.nome + (n.regione ? ' – ' + n.regione : '')),
          h('button', { class: 'btn-testo', onclick: async () => { try { await NT.api('PATCH', '/api/nevi/' + n.id, { archiviato: false }); await NT.ricaricaNei(); aggiornaMarcatori(); renderPannello(); } catch (e) { NT.errore(e); } } }, 'Ripristina')))) : null,
      !vuoto ? h('p', { class: 'piccolo muted' }, 'Clicca un neo nell\'elenco o sulla mappa per vedere lo storico fotografico.') : null);
  }

  /* ------------------------------ dettaglio neo ------------------------------ */
  function pannelloNeo() {
    const n = dett.nevo, foto = dett.foto;
    const salva = async (campi) => { try { await NT.api('PATCH', '/api/nevi/' + n.id, campi); await ricaricaDettaglio(); } catch (e) { NT.errore(e); } };

    const nome = h('input', { type: 'text', class: 'campo titolo-modifica', maxlength: 60, value: n.nome, 'aria-label': 'Nome del neo',
      onchange: () => { if (nome.value.trim()) salva({ nome: nome.value }); else nome.value = n.nome; } });
    const sede = h('input', { type: 'text', class: 'campo', maxlength: 80, list: 'sedi-utili', value: n.regione, placeholder: 'Sede',
      onchange: () => salva({ regione: sede.value }) });
    const note = h('textarea', { class: 'campo', rows: 2, maxlength: 1000, placeholder: 'Note sul neo…', onchange: () => salva({ note: note.value }) }, n.note);

    const testa = h('div', { class: 'scheda' },
      h('div', { class: 'neo-testa' },
        h('button', { class: 'btn-testo', onclick: () => tornaLista() }, '← Tutti i nei'),
        h('span', { class: 'spazio' }),
        h('button', { class: 'btn-icona', title: 'Centra sulla mappa', onclick: () => mappa.centraSu(n, 5) }, NT.icona('mirino')),
        h('button', { class: 'btn-icona', title: 'Stampa la scheda di questo neo', onclick: () => NT.stampaNei([n.id]) }, NT.icona('stampa')),
        h('button', { class: 'btn-icona', title: 'Archivia (toglie dalla mappa, conserva i dati)', onclick: async () => {
          await salva({ archiviato: true }); tornaLista(); NT.toast('Neo archiviato. Lo trovi in fondo all\'elenco.', 'ok'); } }, NT.icona('archivio')),
        h('button', { class: 'btn-icona pericolo', title: 'Elimina questo neo e le sue foto', onclick: async () => {
          const si = await NT.conferma('Eliminare «' + n.nome + '»?', 'Verranno cancellate per sempre tutte le sue ' + foto.length + ' foto e i rapporti di analisi.',
            { si: 'Elimina', pericolo: true, scrivi: foto.length ? n.nome : null });
          if (!si) return;
          try { await NT.api('DELETE', '/api/nevi/' + n.id); await NT.ricaricaNei(); tornaLista(); NT.toast('Neo eliminato.', 'ok'); } catch (e) { NT.errore(e); } } }, NT.icona('cestino'))),
      h('div', { class: 'neo-titolo' }, h('span', { class: 'neo-num grande' + (foto.length ? '' : ' vuoto') }, numDi(n.id)), nome),
      h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, 'Sede', sede,
        h('datalist', { id: 'sedi-utili' }, SEDI_UTILI.map(s => h('option', { value: s })))),
        h('div', { class: 'etichetta' }, 'Posizione', h('div', { class: 'piccolo' }, testoPos(n), h('br'), 'Trascina il pallino sulla mappa per spostarlo.'))),
      h('label', { class: 'etichetta' }, 'Note', note));

    const sezioni = [testa, sezioneStorico(n, foto), formFoto(n)];
    const grafico = graficoDiametro(foto);
    if (grafico) sezioni.push(grafico);
    sezioni.push(h('div', { class: 'scheda', id: 'box-analisi' }, h('h3', {}, 'Analisi automatica'), NT.caricamento('Controllo lo stato…')));
    return h('div', { class: 'pila' }, sezioni);
  }

  /* ----------------------------- storico fotografico ----------------------------- */
  function sezioneStorico(n, foto) {
    if (!foto.length) {
      return h('div', { class: 'scheda' }, h('h3', {}, 'Storico fotografico'),
        NT.vuoto('Ancora nessuna foto', 'Aggiungi qui sotto la prima foto: sarà il punto di partenza per vedere se il neo cambia nel tempo.'));
    }
    const f = foto.find(x => x.id === fotoSel) || foto[foto.length - 1];
    const striscia = h('div', { class: 'striscia' }, foto.map(x => h('button', { class: 'miniatura' + (x.id === f.id ? ' sel' : ''), title: NT.fmtData(x.scattata_il) + (x.diametro_mm ? ' · ' + NT.num(x.diametro_mm) + ' mm' : ''),
      onclick: () => { fotoSel = x.id; renderPannello(); } },
      h('img', { src: '/foto/' + x.id + '/mini?l=240', alt: 'Foto del ' + NT.fmtData(x.scattata_il), loading: 'lazy' }),
      h('span', { class: 'data' }, NT.fmtData(x.scattata_il)),
      x.esito && x.esito !== 'nessuno' ? h('i', { class: 'punto-esito ' + NT.ESITI[x.esito].cls, title: NT.ESITI[x.esito].testo }) : null)));
    const precedente = foto[foto.indexOf(f) - 1];
    const meta = h('div', { class: 'foto-meta' },
      h('span', {}, h('strong', {}, NT.fmtData(f.scattata_il)), ' · ', f.tipo === 'dermoscopica' ? 'dermoscopica' : 'foto normale'),
      f.diametro_mm ? h('span', {}, 'Diametro: ', h('strong', {}, NT.num(f.diametro_mm) + ' mm'),
        precedente && precedente.diametro_mm ? h('span', { class: 'delta' }, ' (' + (f.diametro_mm - precedente.diametro_mm >= 0 ? '+' : '') + NT.num(f.diametro_mm - precedente.diametro_mm) + ' mm dalla foto precedente)') : null) : null,
      f.note ? h('span', { class: 'muted' }, f.note) : null);
    return h('div', { class: 'scheda' },
      h('div', { class: 'testa-lista' }, h('h3', {}, 'Storico fotografico (' + foto.length + ')'),
        foto.length >= 2 ? h('button', { class: 'btn-testo', onclick: () => dialogoConfronto(foto, f) }, NT.icona('confronta', 16), 'Confronta') : null),
      striscia,
      h('button', { class: 'anteprima', title: 'Clic per vedere la foto originale a schermo intero', onclick: () => apriLightbox(f) },
        h('img', { src: '/foto/' + f.id + '/mini?l=960', alt: 'Foto del ' + NT.fmtData(f.scattata_il) })),
      meta,
      h('div', { class: 'azioni-foto' },
        h('button', { class: 'btn-testo', onclick: () => dialogoModificaFoto(f) }, 'Modifica data/misura'),
        h('button', { class: 'btn-testo pericolo', onclick: async () => {
          const si = await NT.conferma('Eliminare questa foto?', 'La foto del ' + NT.fmtData(f.scattata_il) + ' e il suo rapporto di analisi saranno cancellati per sempre.', { si: 'Elimina foto', pericolo: true });
          if (!si) return;
          try { await NT.api('DELETE', '/api/foto/' + f.id); await ricaricaDettaglio(); fotoSel = dett.foto.length ? dett.foto[dett.foto.length - 1].id : null; renderPannello(); NT.toast('Foto eliminata.', 'ok'); } catch (e) { NT.errore(e); } } }, 'Elimina foto')));
  }

  function apriLightbox(f) {
    const d = $('#lightbox');
    d.replaceChildren(h('div', { class: 'lb' },
      h('div', { class: 'lb-barra' }, h('strong', {}, NT.fmtData(f.scattata_il)), h('span', { class: 'spazio' }), h('button', { class: 'btn', onclick: () => d.close() }, 'Chiudi')),
      h('img', { src: '/foto/' + f.id + '/originale', alt: 'Foto originale' })));
    d.showModal();
  }

  function dialogoModificaFoto(f) {
    const data = h('input', { type: 'date', class: 'campo', value: f.scattata_il, max: NT.oggiISO() });
    const diam = h('input', { type: 'text', class: 'campo', inputmode: 'decimal', value: f.diametro_mm === null ? '' : NT.num(f.diametro_mm), placeholder: 'es. 4,5' });
    const tipo = h('select', { class: 'campo' }, h('option', { value: 'normale', selected: f.tipo === 'normale' }, 'Foto normale'), h('option', { value: 'dermoscopica', selected: f.tipo === 'dermoscopica' }, 'Dermoscopica'));
    const nota = h('textarea', { class: 'campo', rows: 2, maxlength: 1000 }, f.note);
    NT.apriDialogo(h('div', {}, h('h3', {}, 'Modifica foto'),
      h('label', { class: 'etichetta' }, 'Data dello scatto', data), h('label', { class: 'etichetta' }, 'Diametro (mm)', diam),
      h('label', { class: 'etichetta' }, 'Tipo', tipo), h('label', { class: 'etichetta' }, 'Note', nota),
      h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => NT.chiudiDialogo() }, 'Annulla'),
        h('button', { class: 'btn btn-pri', onclick: async () => {
          try {
            await NT.api('PATCH', '/api/foto/' + f.id, { scattata_il: data.value, diametro_mm: diam.value, tipo: tipo.value, note: nota.value });
            NT.chiudiDialogo(); await ricaricaDettaglio(); renderPannello();
          } catch (e) { NT.errore(e); }
        } }, 'Salva'))));
  }

  /* ----------------------------- aggiunta di una foto ----------------------------- */
  function formFoto(n) {
    let file = null;
    const anteprima = h('div', { class: 'drop-testo' }, NT.icona('foto', 26), h('span', {}, 'Trascina qui una foto oppure clicca per sceglierla'), h('small', {}, 'JPG, PNG, WEBP o BMP · fino a 60 MB'));
    const input = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/bmp,.jpg,.jpeg,.png,.webp,.bmp', class: 'nascosto' });
    const drop = h('label', { class: 'drop' }, input, anteprima);
    const data = h('input', { type: 'date', class: 'campo', value: NT.oggiISO(), max: NT.oggiISO(), oninput: () => { usaExif.checked = false; } });
    const usaExif = h('input', { type: 'checkbox', checked: true });
    const tipo = h('select', { class: 'campo' }, h('option', { value: 'normale' }, 'Foto normale (smartphone)'), h('option', { value: 'dermoscopica' }, 'Dermoscopica'));
    const diam = h('input', { type: 'text', class: 'campo', inputmode: 'decimal', placeholder: 'es. 4,5' });
    const nota = h('input', { type: 'text', class: 'campo', maxlength: 1000, placeholder: 'Facoltativa' });
    const analizza = h('input', { type: 'checkbox', checked: true });
    const btn = h('button', { class: 'btn btn-pri', disabled: true }, NT.icona('foto', 18), 'Salva foto');

    function scegli(fl) {
      if (!fl) return;
      if (!/^image\//.test(fl.type) && !/\.(jpe?g|png|webp|bmp)$/i.test(fl.name)) { NT.toast('Scegli un file immagine (JPG, PNG, WEBP o BMP).', 'errore'); return; }
      if (fl.size > (S.stato.max_mb_foto || 60) * 1048576) { NT.toast('La foto supera i ' + (S.stato.max_mb_foto || 60) + ' MB: riducila o scegline un\'altra.', 'errore'); return; }
      file = fl;
      data.value = NT.dataDaMs(fl.lastModified); usaExif.checked = true;
      const url = URL.createObjectURL(fl);
      anteprima.replaceChildren(h('img', { src: url, alt: 'Anteprima', class: 'drop-img' }), h('small', {}, fl.name + ' · ' + (fl.size / 1048576).toFixed(1).replace('.', ',') + ' MB · clicca per cambiare'));
      btn.disabled = false;
    }
    input.addEventListener('change', () => scegli(input.files[0]));
    ['dragenter', 'dragover'].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.add('sopra'); }));
    ['dragleave', 'drop'].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.remove('sopra'); }));
    drop.addEventListener('drop', ev => scegli(ev.dataTransfer.files[0]));

    btn.addEventListener('click', async () => {
      if (!file) return;
      btn.disabled = true; btn.replaceChildren(h('span', { class: 'spinner' }), 'Salvataggio…');
      const q = new URLSearchParams({ data: data.value, exif: usaExif.checked ? '1' : '0', tipo: tipo.value, diametro: diam.value, note: nota.value, analizza: analizza.checked ? '1' : '0' });
      try {
        const r = await NT.api('POST', '/api/nevi/' + n.id + '/foto?' + q.toString(), null, { raw: file, tipo: file.type || 'application/octet-stream' });
        formFotoAperto = false;
        await ricaricaDettaglio();
        fotoSel = r.id;
        renderPannello();
        NT.toast('Foto salvata (' + NT.fmtData(r.scattata_il) + (r.da_exif ? ', data letta dalla foto' : '') + ').' + (r.analisi_errore ? ' ' + r.analisi_errore : ''), r.analisi_errore ? 'errore' : 'ok');
      } catch (e) { btn.disabled = false; btn.replaceChildren(NT.icona('foto', 18), 'Salva foto'); NT.errore(e); }
    });

    const det = h('details', { class: 'scheda form-foto', open: formFotoAperto || dett.foto.length === 0 },
      h('summary', {}, NT.icona('piu', 16), 'Aggiungi una foto allo storico'),
      h('div', { class: 'form-corpo' }, drop,
        h('div', { class: 'riga-2' },
          h('label', { class: 'etichetta' }, 'Data dello scatto', data,
            h('span', { class: 'spunta' }, usaExif, ' Usa la data scritta nella foto, se c\'è')),
          h('label', { class: 'etichetta' }, 'Diametro misurato (mm)', diam)),
        h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, 'Tipo di foto', tipo), h('label', { class: 'etichetta' }, 'Note', nota)),
        h('label', { class: 'spunta grande' }, analizza, ' Analizza subito con tutti i metodi installati'),
        h('details', { class: 'consigli' }, h('summary', {}, 'Come scattare foto confrontabili'),
          h('ul', {}, h('li', {}, 'Stessa luce (luce del giorno, senza flash) e stessa distanza ogni volta, circa 10-15 cm.'),
            h('li', {}, 'Metti accanto al neo un righello o una moneta: serve per misurare il diametro.'),
            h('li', {}, 'Foto a fuoco, con il neo al centro e la pelle ben visibile (sposta i peli, se serve).'),
            h('li', {}, 'Scatta sempre dalla stessa angolazione e salva l\'originale, senza filtri.'))),
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
    let s = '<svg viewBox="0 0 ' + L + ' ' + A + '" class="grafico" role="img" aria-label="Diametro del neo nel tempo">';
    for (let v = 0; v <= vmax; v += passo) s += '<line x1="' + ml + '" x2="' + (L - mr) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" class="gl"/><text x="' + (ml - 6) + '" y="' + (Y(v) + 4) + '" text-anchor="end" class="gt">' + v + '</text>';
    s += '<line x1="' + ml + '" x2="' + (L - mr) + '" y1="' + Y(6) + '" y2="' + Y(6) + '" class="g6"/><text x="' + (L - mr) + '" y="' + (Y(6) - 4) + '" text-anchor="end" class="gt g6t">6 mm</text>';
    s += '<polyline class="gline" points="' + pt.map(p => X(p.d) + ',' + Y(p.v)).join(' ') + '"/>';
    pt.forEach(p => { s += '<circle cx="' + X(p.d) + '" cy="' + Y(p.v) + '" r="4.5" class="gp"><title>' + NT.fmtData(p.d) + ': ' + NT.num(p.v) + ' mm</title></circle>'; });
    s += '<text x="' + X(pt[0].d) + '" y="' + (A - 10) + '" text-anchor="start" class="gt">' + NT.fmtData(pt[0].d) + '</text>';
    s += '<text x="' + X(pt[pt.length - 1].d) + '" y="' + (A - 10) + '" text-anchor="end" class="gt">' + NT.fmtData(pt[pt.length - 1].d) + '</text></svg>';
    const diff = pt[pt.length - 1].v - pt[0].v, giorni = NT.giorniTra(pt[0].d, pt[pt.length - 1].d);
    return h('div', { class: 'scheda' }, h('h3', {}, 'Diametro nel tempo'), NT.html(s),
      h('p', { class: 'piccolo' }, 'Variazione: ', h('strong', {}, (diff >= 0 ? '+' : '') + NT.num(diff) + ' mm'), ' in ' + giorni + ' giorni. ',
        'Sono misure inserite da te: valgono se prese sempre allo stesso modo. Un neo che cresce o cambia è un buon motivo per farlo vedere al dermatologo; la linea a 6 mm è solo il riferimento classico dei criteri ABCDE.'),
      h('button', { class: 'btn-testo', onclick: dialogoABCDE }, 'Promemoria ABCDE'));
  }

  function dialogoABCDE() {
    const voci = [['A', 'Asimmetria', 'Le due metà del neo non si somigliano.'], ['B', 'Bordi', 'Irregolari, frastagliati o sfumati.'],
      ['C', 'Colore', 'Più colori nello stesso neo (marrone, nero, rosso, blu, bianco).'], ['D', 'Diametro', 'Più di 6 mm (ma esistono melanomi più piccoli).'],
      ['E', 'Evoluzione', 'Cambia nel tempo: forma, colore, dimensione, rilievo, o compaiono prurito o sanguinamento.']];
    NT.apriDialogo(h('div', {}, h('h3', {}, 'Promemoria ABCDE'),
      h('ul', { class: 'abcde' }, voci.map(([l, t, d]) => h('li', {}, h('b', {}, l), h('span', {}, h('strong', {}, t), ' – ', d)))),
      h('p', { class: 'piccolo' }, 'Conta anche il «brutto anatroccolo»: un neo diverso da tutti gli altri. I noduli che crescono rapidamente o sono duri al tatto vanno mostrati subito. Questo promemoria non sostituisce la visita.'),
      h('div', { class: 'azioni' }, h('button', { class: 'btn btn-pri', onclick: () => NT.chiudiDialogo() }, 'Chiudi'))));
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
    const modoBtn = h('button', { class: 'btn', onclick: () => { sovrapposto = !sovrapposto; modoBtn.textContent = sovrapposto ? 'Mostra affiancate' : 'Sovrapponi con cursore'; ridisegna(); } }, 'Sovrapponi con cursore');
    function ridisegna() {
      const giorni = NT.giorniTra(a.scattata_il, b.scattata_il);
      const dd = (a.diametro_mm && b.diametro_mm) ? ' Diametro: ' + NT.num(b.diametro_mm - a.diametro_mm) + ' mm di differenza.' : '';
      const nota = h('p', { class: 'piccolo' }, 'Tra le due foto sono passati ' + Math.abs(giorni) + ' giorni.' + dd + ' Confronta forma, bordi e colori: se noti differenze, mostra le foto al dermatologo.');
      if (!sovrapposto) {
        area.replaceChildren(h('div', { class: 'confronto-coppia' },
          h('figure', {}, h('img', { src: '/foto/' + a.id + '/mini?l=960', alt: '' }), h('figcaption', {}, etich(a))),
          h('figure', {}, h('img', { src: '/foto/' + b.id + '/mini?l=960', alt: '' }), h('figcaption', {}, etich(b)))), nota);
      } else {
        const top = h('img', { src: '/foto/' + a.id + '/mini?l=960', alt: '', class: 'sopra', style: { clipPath: 'inset(0 ' + (100 - posizione) + '% 0 0)' } });
        const cur = h('input', { type: 'range', min: 0, max: 100, value: posizione, 'aria-label': 'Cursore di confronto', oninput: () => { posizione = +cur.value; top.style.clipPath = 'inset(0 ' + (100 - posizione) + '% 0 0)'; } });
        area.replaceChildren(h('div', { class: 'sovrapposte' }, h('img', { src: '/foto/' + b.id + '/mini?l=960', alt: '' }), top),
          cur, h('div', { class: 'didascalie' }, h('span', {}, '← ' + etich(a)), h('span', {}, etich(b) + ' →')), nota);
      }
    }
    ridisegna();
    NT.apriDialogo(h('div', {}, h('h3', {}, 'Confronto tra due foto'),
      h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, 'Prima', selA), h('label', { class: 'etichetta' }, 'Dopo', selB)),
      modoBtn, area, h('div', { class: 'azioni' }, h('button', { class: 'btn btn-pri', onclick: () => NT.chiudiDialogo() }, 'Chiudi'))), true);
  }

  /* ------------------------------ analisi automatica ------------------------------ */
  async function caricaAnalisi(fotoId) {
    const box = $('#box-analisi');
    if (!box || fotoId !== fotoSel) return;
    let st;
    try { st = await NT.get('/api/foto/' + fotoId + '/analisi'); } catch (e) { box.replaceChildren(h('h3', {}, 'Analisi automatica'), h('p', { class: 'errore-campo' }, e.message)); return; }
    if (fotoId !== fotoSel || !$('#box-analisi')) return;
    const attiva = st.stato === 'in_coda' || st.stato === 'in_corso';
    if (attiva) inAnalisi.add(fotoId);
    else if (inAnalisi.has(fotoId)) {                          // appena finita: aggiorno elenco e pallini
      inAnalisi.delete(fotoId);
      await ricaricaDettaglio();
      renderPannello();
      return;
    }
    box.replaceChildren(h('h3', {}, 'Analisi automatica'), contenutoAnalisi(fotoId, st));
    if (attiva) pollTimer = setTimeout(() => caricaAnalisi(fotoId), 3000);
  }

  async function avviaAnalisi(fotoId) {
    try { await NT.api('POST', '/api/foto/' + fotoId + '/analizza'); inAnalisi.add(fotoId); caricaAnalisi(fotoId); } catch (e) { NT.errore(e); }
  }

  function contenutoAnalisi(fotoId, st) {
    if (st.stato === 'nessuna') {
      return h('div', {}, h('p', {}, 'Questa foto non è ancora stata analizzata. L\'analisi confronta più metodi sulla stessa immagine e ti dice cosa ha risposto ciascuno.'),
        h('p', { class: 'piccolo muted' }, 'La prima analisi può richiedere diversi minuti (i modelli vengono caricati in memoria). ' +
          (st.skinsense_attivo ? 'SkinSense è attivo: la foto (senza metadati) verrà inviata a un servizio online.' : 'La foto resta sul tuo computer: SkinSense (servizio online) è disattivato.')),
        h('button', { class: 'btn btn-pri', onclick: () => avviaAnalisi(fotoId) }, 'Analizza questa foto'));
    }
    if (st.stato === 'in_coda' || st.stato === 'in_corso') {
      return h('div', { class: 'analisi-attesa' }, h('div', { class: 'riga-spinner' }, h('span', { class: 'spinner grande' }),
        h('div', {}, h('strong', {}, st.stato === 'in_coda' ? 'In coda' + (st.posizione_coda > 0 ? ' (posizione ' + st.posizione_coda + ')' : '') + '…' : 'Analisi in corso…'),
          h('p', { class: 'piccolo muted' }, 'Puoi continuare a usare l\'app. Se chiudi la finestra l\'analisi non va persa: il programma finisce il lavoro e poi si spegne da solo.'))),
        st.avanzamento && st.avanzamento.length ? h('pre', { class: 'log' }, st.avanzamento.join('\n')) : null);
    }
    if (st.stato === 'errore') {
      return h('div', {}, h('p', { class: 'errore-campo' }, st.messaggio || 'L\'analisi non è riuscita.'),
        h('button', { class: 'btn', onclick: () => avviaAnalisi(fotoId) }, 'Riprova'));
    }
    return renderSintesi(st.sintesi, fotoId);
  }

  const GIUDIZIO_NESSUNO = 'Nessun metodo ha prodotto un risultato: controlla i motivi indicati sotto.';
  const GIUDIZIO_ATT = 'Almeno un metodo (o un suo modello) segnala una lesione da attenzionare. Non è una diagnosi e questi strumenti sbagliano spesso, ma è un motivo in più per non rimandare la visita dermatologica e per portare questo rapporto.';
  const GIUDIZIO_BEN = 'Nessuno dei metodi che hanno risposto segnala la lesione come sospetta. Questo NON esclude un melanoma: gli strumenti non sono validati clinicamente e sbagliano anche in questa direzione. Se il neo è asimmetrico, ha bordi irregolari, colori diversi, è più grande di 6 mm o è cambiato nel tempo, la visita resta necessaria.';
  const AVVERTENZE = [
    'Questo rapporto NON è una diagnosi. I programmi usati sono prototipi di ricerca, non dispositivi medici.',
    'I metodi sono addestrati su fotografie diverse dalle tue: cambiare luce, distanza o fotocamera può cambiare la risposta.',
    'Fototipo, età e familiarità non cambiano il risultato delle reti neurali (guardano solo i pixel): servono a contestualizzare il rischio.',
    'Se i metodi sono in disaccordo è normale: significa solo che nessuno di loro è affidabile da solo.',
  ];

  function renderSintesi(s, fotoId) {
    const giud = s.con_risultato.length === 0 ? GIUDIZIO_NESSUNO : (s.attenzione.length || s.discordi.length) ? GIUDIZIO_ATT : GIUDIZIO_BEN;
    const schede = s.metodi.map(m => {
      const ok = m.risultati.filter(r => r.stato === 'ok');
      const piu = new Set(m.risultati.map(r => r.gruppo).filter(Boolean)).size > 1;
      return h('div', { class: 'metodo' },
        h('div', { class: 'metodo-testa' }, h('strong', {}, 'Metodo ' + m.numero), h('span', { class: 'metodo-titolo' }, m.titolo),
          m.verdetto ? NT.chipEsito(m.verdetto) : h('span', { class: 'chip chip-neutro' }, 'Nessun risultato')),
        m.introduzione ? h('p', { class: 'piccolo muted' }, m.introduzione) : null,
        ok.length ? h('p', { class: 'ha-detto' }, 'Il metodo ' + m.numero + ' ha detto che: ', h('strong', {}, m.frase)) : null,
        h('ul', { class: 'modelli' }, m.risultati.map(r => r.stato === 'ok'
          ? h('li', {}, h('span', { class: 'mod-nome' }, (piu && r.gruppo ? '[' + r.gruppo + '] ' : '') + r.nome), h('span', {}, '→ ' + r.etichetta),
            h('span', { class: 'muted' }, 'sicurezza ' + NT.perc(r.valore) + (r.prob_mel !== null && r.prob_mel !== undefined ? ' · prob. melanoma ' + NT.perc(r.prob_mel) : '')))
          : h('li', { class: 'nota-metodo ' + r.stato }, h('span', {}, (r.stato === 'errore' ? r.nome + ': errore. ' : r.stato === 'non_disponibile' ? r.nome + ': non disponibile. ' : '') + (r.nota || ''))))));
    });
    return h('div', { class: 'sintesi' },
      h('div', { class: 'sintesi-testa' }, NT.chipEsito(s.esito), h('span', { class: 'piccolo muted' }, s.con_risultato.length + ' metodi su ' + s.metodi.length + ' hanno risposto')),
      h('p', { class: 'giudizio' }, giud),
      schede,
      h('details', { class: 'consigli' }, h('summary', {}, 'Avvertenze'), h('ul', {}, AVVERTENZE.map(a => h('li', {}, a)))),
      s.testo ? h('details', { class: 'consigli' }, h('summary', {}, 'Rapporto completo (testo)'), h('pre', { class: 'rapporto' }, s.testo)) : null,
      h('button', { class: 'btn-testo', onclick: () => avviaAnalisi(fotoId) }, 'Rianalizza'));
  }
})();
