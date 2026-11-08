/* ============================================================================
   stampa.js - scheda stampabile per il dermatologo (mappa, storico, misure)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  /* I valori del profilo sono codici italiani salvati nel database: qui diventano frasi nella lingua scelta.
     Ogni frase è intera (non "capelli" + colore) perché l'accordo cambia da lingua a lingua. */
  const SESSO = { F: NT.t('donna'), M: NT.t('uomo'), altro: NT.t('altro') };
  const FOTOTIPI = ['I', 'II', 'III', 'IV', 'V', 'VI'];
  const CAPELLI = { neri: NT.t('capelli neri'), castani: NT.t('capelli castani'), biondi: NT.t('capelli biondi'), rossi: NT.t('capelli rossi'), grigi: NT.t('capelli grigi o bianchi') };
  const OCCHI = { scuri: NT.t('occhi scuri'), verdi: NT.t('occhi verdi'), azzurri: NT.t('occhi azzurri o grigi') };
  const EFELIDI = { nessuna: NT.t('nessuna efelide'), poche: NT.t('poche efelidi'), molte: NT.t('molte efelidi') };
  const N_NEVI = { '<25': NT.t('meno di 25'), '25-49': '25–49', '50-99': '50–99', '100+': NT.t('100 o più') };
  const ATIPICI = { no: NT.t('no'), si: NT.t('sì'), 'non so': NT.t('non so') };
  const SCOTTATURE = { mai: NT.t('mai'), poche: NT.t('poche'), molte: NT.t('molte') };
  const LAMPADE = { mai: NT.t('mai'), alcune: NT.t('qualche volta'), spesso: NT.t('spesso') };
  const TEST_GEN = { si_positivo: NT.t('sì, positivo'), si_negativo: NT.t('sì, negativo'), si_non_informativo: NT.t('sì, non informativo') };
  const ESITO_STAMPA = {
    attenzione: NT.t('tutti i metodi con risultato indicano un neo da attenzionare'),
    discordante: NT.t('i metodi non concordano tra loro'),
    benigno: NT.t('nessun metodo ha segnalato il neo (questo non esclude un melanoma)'),
    nessuno: NT.t('nessun risultato disponibile'),
  };
  const lab = (tab, codice) => tab[codice] || codice;

  function riepilogoProfilo(u) {
    const p = u.profilo, righe = [];
    if (u.eta !== null && u.eta !== undefined) righe.push([NT.t('Età'), NT.tp(u.eta, '{n} anno', '{n} anni')]);
    if (p.sesso) righe.push([NT.t('Sesso'), lab(SESSO, p.sesso)]);
    if (p.fototipo) righe.push([NT.t('Fototipo'), FOTOTIPI[p.fototipo - 1]]);
    const fen = [p.capelli && lab(CAPELLI, p.capelli), p.occhi && lab(OCCHI, p.occhi), p.efelidi && lab(EFELIDI, p.efelidi)].filter(Boolean).join(', ');
    if (fen) righe.push([NT.t('Aspetto'), fen]);
    if (p.n_nevi) righe.push([NT.t('Numero di nei'), lab(N_NEVI, p.n_nevi)]);
    if (p.nevi_atipici) righe.push([NT.t('Nei atipici'), lab(ATIPICI, p.nevi_atipici)]);
    if (p.scottature) righe.push([NT.t('Scottature'), lab(SCOTTATURE, p.scottature)]);
    if (p.lampade) righe.push([NT.t('Lampade abbronzanti'), lab(LAMPADE, p.lampade)]);
    if (p.melanomi_personali) righe.push([NT.t('Melanomi già diagnosticati'), String(p.melanomi_personali)]);
    if (p.fam_compilata) {
      const f = [];
      if (p.fam_melanoma_1grado) f.push(NT.t('{n} parente/i di primo grado con melanoma', { n: p.fam_melanoma_1grado }));
      if (p.fam_melanoma_altri) f.push(NT.t('{n} altro/i parente/i con melanoma', { n: p.fam_melanoma_altri }));
      if (p.fam_pancreas) f.push(NT.t('{n} con tumore del pancreas', { n: p.fam_pancreas }));
      if (p.fam_astrocitoma) f.push(NT.t('{n} con astrocitoma', { n: p.fam_astrocitoma }));
      if (p.fam_uveale) f.push(NT.t('{n} con melanoma uveale', { n: p.fam_uveale }));
      righe.push([NT.t('Storia familiare'), f.length ? f.join('; ') : NT.t('nessun caso indicato')]);
    }
    if (p.test_genetico && p.test_genetico !== 'no') righe.push([NT.t('Test genetico già eseguito'), lab(TEST_GEN, p.test_genetico)]);
    return righe;
  }

  function mappaStampa(nei) {
    const ft = S.utente.profilo.fototipo || 0;
    const radice = NT.html(window.Corpo.svgCompleto(ft));
    const g = radice.querySelector('.marcatori');
    const NSV = 'http://www.w3.org/2000/svg';
    nei.forEach((n, i) => {
      const x = (n.vista === 'retro' ? 400 : 0) + n.x * 400, y = 20 + n.y * 900;
      const gr = document.createElementNS(NSV, 'g');
      gr.setAttribute('transform', 'translate(' + x.toFixed(1) + ',' + y.toFixed(1) + ')');
      const c = document.createElementNS(NSV, 'circle'); c.setAttribute('r', '19'); c.setAttribute('class', 'st-punto');
      const t = document.createElementNS(NSV, 'text'); t.setAttribute('y', '7'); t.setAttribute('text-anchor', 'middle'); t.setAttribute('class', 'st-num'); t.textContent = String(i + 1);
      gr.append(c, t); g.appendChild(gr);
    });
    radice.setAttribute('class', 'corpo-svg mappa-stampa');
    return radice;
  }

  function schedaNeo(num, n, foto) {
    const prima = foto[0], ultima = foto[foto.length - 1];
    let variazione = null;
    if (foto.length > 1) {
      const giorni = NT.giorniTra(prima.scattata_il, ultima.scattata_il);
      const dd = (prima.diametro_mm && ultima.diametro_mm) ? ' ' + NT.t('Diametro: da {da} a {a} mm.', { da: NT.num(prima.diametro_mm), a: NT.num(ultima.diametro_mm) }) : '';
      variazione = NT.t('{n} foto in {giorni} (dal {da} al {a}).', { n: foto.length, giorni: NT.tp(giorni, '{n} giorno', '{n} giorni'), da: NT.fmtData(prima.scattata_il), a: NT.fmtData(ultima.scattata_il) }) + dd;
    }
    const mostra = foto.length <= 8 ? foto : [foto[0], foto[1]].concat(foto.slice(-6));
    return h('section', { class: 'st-neo' },
      h('h3', {}, h('span', { class: 'st-badge' }, num), ' ', n.nome, n.regione ? ' – ' + NT.tr(n.regione) : ' – ' + (n.vista === 'retro' ? NT.t('retro') : NT.t('fronte'))),
      n.note ? h('p', { class: 'st-nota' }, NT.t('Note:') + ' ' + n.note) : null,
      foto.length ? [
        variazione ? h('p', {}, variazione) : h('p', {}, prima.diametro_mm ? NT.t('1 foto del {data}, diametro {mm} mm.', { data: NT.fmtData(prima.scattata_il), mm: NT.num(prima.diametro_mm) }) : NT.t('1 foto del {data}.', { data: NT.fmtData(prima.scattata_il) })),
        h('div', { class: 'st-foto' }, mostra.map(f => h('figure', {}, h('img', { src: '/foto/' + f.id + '/mini?l=480', alt: NT.t('Foto del {data}', { data: NT.fmtData(f.scattata_il) }) }),
          h('figcaption', {}, NT.fmtData(f.scattata_il), f.diametro_mm ? ' · ' + NT.num(f.diametro_mm) + ' mm' : '', f.tipo === 'dermoscopica' ? ' · ' + NT.t('dermoscopica') : '')))),
        foto.length > mostra.length ? h('p', { class: 'st-nota' }, NT.t('Sono mostrate {n} foto su {tot}.', { n: mostra.length, tot: foto.length })) : null,
        ultima.esito ? h('p', { class: 'st-nota' }, NT.t('Ultima analisi automatica ({data}): {esito}. Strumento di ricerca, non diagnostico.', { data: NT.fmtData(ultima.scattata_il), esito: ESITO_STAMPA[ultima.esito] || ultima.esito })) : null,
      ] : h('p', { class: 'st-nota' }, NT.t('Nessuna foto ancora registrata.')));
  }

  NT.stampaNei = async function (ids) {
    if (!S.utente) return;
    const area = NT.$('#stampa');
    try {
      NT.toast(NT.t('Preparo la scheda…'), 'info');
      await NT.ricaricaUtente();
      await NT.ricaricaNei();
      const scelti = S.nei.filter(n => !n.archiviato && (!ids || ids.includes(n.id)));
      if (!scelti.length) { NT.toast(NT.t('Non ci sono nei da stampare.'), 'errore'); return; }
      const dettagli = await Promise.all(scelti.map(n => NT.get('/api/nevi/' + n.id)));
      const tutti = S.nei.filter(n => !n.archiviato);
      const numero = id => tutti.findIndex(n => n.id === id) + 1;
      const u = S.utente, rischio = u.rischio.presenti;
      const prof = riepilogoProfilo(u);
      const nuovo = h('div', { class: 'st-pagina' },
        h('header', { class: 'st-testata' }, h('div', {}, h('h1', {}, NT.t('Scheda dei nei – {nome}', { nome: u.nome })), h('div', { class: 'st-sotto' }, NT.t('Stampata il {data} con NeoTracker', { data: NT.fmtData(NT.oggiISO()) }))),
          h('div', { class: 'st-sotto' }, NT.tp(scelti.length, '{n} neo in questa scheda', '{n} nei in questa scheda'))),
        h('section', { class: 'st-profilo' }, h('h2', {}, NT.t('Dati della persona')),
          prof.length ? h('dl', {}, prof.map(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])) : h('p', { class: 'st-nota' }, NT.t('Profilo non compilato.')),
          rischio.length ? h('p', {}, h('strong', {}, NT.t('Fattori di rischio indicati:') + ' '), rischio.map(r => NT.tr(r.etichetta)).join('; ') + '.') : null),
        h('section', {}, h('h2', {}, NT.t('Dove si trovano')), mappaStampa(scelti.map(n => Object.assign({}, n))),
          h('p', { class: 'st-nota' }, NT.t('I numeri corrispondono alle schede seguenti. Sulla figura: a sinistra la vista frontale, a destra quella posteriore.'))),
        dettagli.map(d => schedaNeo(numero(d.nevo.id), d.nevo, d.foto)),
        h('footer', { class: 'st-avviso' }, NT.t('Questa scheda raccoglie dati inseriti dalla persona e foto da lei scattate. I risultati dell\'analisi automatica sono sperimentali, non sono una diagnosi e non sostituiscono la visita dermatologica o la dermoscopia.')));
      // numeri coerenti con la mappa: usa la numerazione globale, non quella della selezione
      NT.$$('.st-num', nuovo).forEach((t, i) => { t.textContent = String(numero(scelti[i].id)); });
      area.replaceChildren(nuovo);
      const imgs = NT.$$('img', area);
      await Promise.all(imgs.map(im => new Promise(r => { if (im.complete) r(); else { im.addEventListener('load', r, { once: true }); im.addEventListener('error', r, { once: true }); } })));
      const pulisci = () => { area.replaceChildren(); window.removeEventListener('afterprint', pulisci); };
      window.addEventListener('afterprint', pulisci);
      document.body.classList.add('in-stampa');
      window.print();
      setTimeout(() => document.body.classList.remove('in-stampa'), 1000);
    } catch (e) { NT.errore(e); }
  };
})();
