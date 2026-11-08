/* ============================================================================
   stampa.js - scheda stampabile per il dermatologo (mappa, storico, misure)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  const SESSO = { F: 'donna', M: 'uomo', altro: 'altro' };
  const FOTOTIPI = ['I', 'II', 'III', 'IV', 'V', 'VI'];
  const ESITO_STAMPA = {
    attenzione: 'tutti i metodi con risultato indicano un neo da attenzionare',
    discordante: 'i metodi non concordano tra loro',
    benigno: 'nessun metodo ha segnalato il neo (questo non esclude un melanoma)',
    nessuno: 'nessun risultato disponibile',
  };

  function riepilogoProfilo(u) {
    const p = u.profilo, righe = [];
    if (u.eta !== null && u.eta !== undefined) righe.push(['Età', u.eta + ' anni']);
    if (p.sesso) righe.push(['Sesso', SESSO[p.sesso] || p.sesso]);
    if (p.fototipo) righe.push(['Fototipo', FOTOTIPI[p.fototipo - 1]]);
    const fen = [p.capelli && 'capelli ' + p.capelli, p.occhi && 'occhi ' + p.occhi, p.efelidi && 'efelidi: ' + p.efelidi].filter(Boolean).join(', ');
    if (fen) righe.push(['Aspetto', fen]);
    if (p.n_nevi) righe.push(['Numero di nei', p.n_nevi]);
    if (p.nevi_atipici) righe.push(['Nei atipici', p.nevi_atipici]);
    if (p.scottature) righe.push(['Scottature', p.scottature]);
    if (p.lampade) righe.push(['Lampade abbronzanti', p.lampade]);
    if (p.melanomi_personali) righe.push(['Melanomi già diagnosticati', String(p.melanomi_personali)]);
    if (p.fam_compilata) {
      const f = [];
      if (p.fam_melanoma_1grado) f.push(p.fam_melanoma_1grado + ' parente/i di primo grado con melanoma');
      if (p.fam_melanoma_altri) f.push(p.fam_melanoma_altri + ' altro/i parente/i con melanoma');
      if (p.fam_pancreas) f.push(p.fam_pancreas + ' con tumore del pancreas');
      if (p.fam_astrocitoma) f.push(p.fam_astrocitoma + ' con astrocitoma');
      if (p.fam_uveale) f.push(p.fam_uveale + ' con melanoma uveale');
      righe.push(['Storia familiare', f.length ? f.join('; ') : 'nessun caso indicato']);
    }
    if (p.test_genetico && p.test_genetico !== 'no') righe.push(['Test genetico già eseguito', { si_positivo: 'sì, positivo', si_negativo: 'sì, negativo', si_non_informativo: 'sì, non informativo' }[p.test_genetico] || p.test_genetico]);
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
      const dd = (prima.diametro_mm && ultima.diametro_mm) ? ' Diametro: da ' + NT.num(prima.diametro_mm) + ' a ' + NT.num(ultima.diametro_mm) + ' mm.' : '';
      variazione = foto.length + ' foto in ' + giorni + ' giorni (dal ' + NT.fmtData(prima.scattata_il) + ' al ' + NT.fmtData(ultima.scattata_il) + ').' + dd;
    }
    const mostra = foto.length <= 8 ? foto : [foto[0], foto[1]].concat(foto.slice(-6));
    return h('section', { class: 'st-neo' },
      h('h3', {}, h('span', { class: 'st-badge' }, num), ' ', n.nome, n.regione ? ' – ' + n.regione : ' – ' + (n.vista === 'retro' ? 'retro' : 'fronte')),
      n.note ? h('p', { class: 'st-nota' }, 'Note: ' + n.note) : null,
      foto.length ? [
        variazione ? h('p', {}, variazione) : h('p', {}, '1 foto del ' + NT.fmtData(prima.scattata_il) + (prima.diametro_mm ? ', diametro ' + NT.num(prima.diametro_mm) + ' mm' : '') + '.'),
        h('div', { class: 'st-foto' }, mostra.map(f => h('figure', {}, h('img', { src: '/foto/' + f.id + '/mini?l=480', alt: 'Foto del ' + NT.fmtData(f.scattata_il) }),
          h('figcaption', {}, NT.fmtData(f.scattata_il), f.diametro_mm ? ' · ' + NT.num(f.diametro_mm) + ' mm' : '', f.tipo === 'dermoscopica' ? ' · dermoscopica' : '')))),
        foto.length > mostra.length ? h('p', { class: 'st-nota' }, 'Sono mostrate ' + mostra.length + ' foto su ' + foto.length + '.') : null,
        ultima.esito ? h('p', { class: 'st-nota' }, 'Ultima analisi automatica (' + NT.fmtData(ultima.scattata_il) + '): ' + (ESITO_STAMPA[ultima.esito] || ultima.esito) + '. Strumento di ricerca, non diagnostico.') : null,
      ] : h('p', { class: 'st-nota' }, 'Nessuna foto ancora registrata.'));
  }

  NT.stampaNei = async function (ids) {
    if (!S.utente) return;
    const area = NT.$('#stampa');
    try {
      NT.toast('Preparo la scheda…', 'info');
      await NT.ricaricaUtente();
      await NT.ricaricaNei();
      const scelti = S.nei.filter(n => !n.archiviato && (!ids || ids.includes(n.id)));
      if (!scelti.length) { NT.toast('Non ci sono nei da stampare.', 'errore'); return; }
      const dettagli = await Promise.all(scelti.map(n => NT.get('/api/nevi/' + n.id)));
      const tutti = S.nei.filter(n => !n.archiviato);
      const numero = id => tutti.findIndex(n => n.id === id) + 1;
      const u = S.utente, rischio = u.rischio.presenti;
      const prof = riepilogoProfilo(u);
      const nuovo = h('div', { class: 'st-pagina' },
        h('header', { class: 'st-testata' }, h('div', {}, h('h1', {}, 'Scheda dei nei – ' + u.nome), h('div', { class: 'st-sotto' }, 'Stampata il ' + NT.fmtData(NT.oggiISO()) + ' con NeoTracker')),
          h('div', { class: 'st-sotto' }, scelti.length + (scelti.length === 1 ? ' neo' : ' nei') + ' in questa scheda')),
        h('section', { class: 'st-profilo' }, h('h2', {}, 'Dati della persona'),
          prof.length ? h('dl', {}, prof.map(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])) : h('p', { class: 'st-nota' }, 'Profilo non compilato.'),
          rischio.length ? h('p', {}, h('strong', {}, 'Fattori di rischio indicati: '), rischio.map(r => r.etichetta).join('; ') + '.') : null),
        h('section', {}, h('h2', {}, 'Dove si trovano'), mappaStampa(scelti.map(n => Object.assign({}, n))),
          h('p', { class: 'st-nota' }, 'I numeri corrispondono alle schede seguenti. Sulla figura: a sinistra la vista frontale, a destra quella posteriore.')),
        dettagli.map(d => schedaNeo(numero(d.nevo.id), d.nevo, d.foto)),
        h('footer', { class: 'st-avviso' }, 'Questa scheda raccoglie dati inseriti dalla persona e foto da lei scattate. I risultati dell\'analisi automatica sono sperimentali, non sono una diagnosi e non sostituiscono la visita dermatologica o la dermoscopia.'));
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
