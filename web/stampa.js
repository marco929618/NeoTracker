/* ============================================================================
   stampa.js - printable sheet for the dermatologist (map, history, measurements)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  /* The profile values are Italian codes saved in the database: here they become sentences in the chosen language.
     Each sentence is whole (not "hair" + colour) because agreement changes from language to language. */
  const SESSO = { F: NT.t('woman'), M: NT.t('man'), altro: NT.t('other') };
  const FOTOTIPI = ['I', 'II', 'III', 'IV', 'V', 'VI'];
  const CAPELLI = { neri: NT.t('black hair'), castani: NT.t('brown hair'), biondi: NT.t('blond hair'), rossi: NT.t('red hair'), grigi: NT.t('grey or white hair') };
  const OCCHI = { scuri: NT.t('dark eyes'), verdi: NT.t('green eyes'), azzurri: NT.t('blue or grey eyes') };
  const EFELIDI = { nessuna: NT.t('no freckles'), poche: NT.t('a few freckles'), molte: NT.t('many freckles') };
  const N_NEVI = { '<25': NT.t('fewer than 25'), '25-49': '25–49', '50-99': '50–99', '100+': NT.t('100 or more') };
  const ATIPICI = { no: NT.t('no'), si: NT.t('yes'), 'non so': NT.t("don't know") };
  const SCOTTATURE = { mai: NT.t('never'), poche: NT.t('a few'), molte: NT.t('many') };
  const LAMPADE = { mai: NT.t('never'), alcune: NT.t('sometimes'), spesso: NT.t('often') };
  const TEST_GEN = { si_positivo: NT.t('yes, positive'), si_negativo: NT.t('yes, negative'), si_non_informativo: NT.t('yes, uninformative') };
  const ESITO_STAMPA = {
    attenzione: NT.t('all methods with a result flag a mole that needs attention'),
    discordante: NT.t('the methods do not agree with each other'),
    benigno: NT.t('no method flagged the mole (this does not rule out a melanoma)'),
    nessuno: NT.t('no result available'),
  };
  const lab = (tab, codice) => tab[codice] || codice;

  function riepilogoProfilo(u) {
    const p = u.profilo, righe = [];
    if (u.eta !== null && u.eta !== undefined) righe.push([NT.t('Age'), NT.tp(u.eta, '{n} year', '{n} years')]);
    if (p.sesso) righe.push([NT.t('Sex'), lab(SESSO, p.sesso)]);
    if (p.fototipo) righe.push([NT.t('Phototype'), FOTOTIPI[p.fototipo - 1]]);
    const fen = [p.capelli && lab(CAPELLI, p.capelli), p.occhi && lab(OCCHI, p.occhi), p.efelidi && lab(EFELIDI, p.efelidi)].filter(Boolean).join(', ');
    if (fen) righe.push([NT.t('Appearance'), fen]);
    if (p.n_nevi) righe.push([NT.t('Number of moles'), lab(N_NEVI, p.n_nevi)]);
    if (p.nevi_atipici) righe.push([NT.t('Atypical moles'), lab(ATIPICI, p.nevi_atipici)]);
    if (p.scottature) righe.push([NT.t('Sunburns'), lab(SCOTTATURE, p.scottature)]);
    if (p.lampade) righe.push([NT.t('Tanning lamps'), lab(LAMPADE, p.lampade)]);
    if (p.melanomi_personali) righe.push([NT.t('Melanomas already diagnosed'), String(p.melanomi_personali)]);
    if (p.fam_compilata) {
      const f = [];
      if (p.fam_melanoma_1grado) f.push(NT.t('{n} first-degree relative(s) with melanoma', { n: p.fam_melanoma_1grado }));
      if (p.fam_melanoma_altri) f.push(NT.t('{n} other relative(s) with melanoma', { n: p.fam_melanoma_altri }));
      if (p.fam_pancreas) f.push(NT.t('{n} with pancreatic cancer', { n: p.fam_pancreas }));
      if (p.fam_astrocitoma) f.push(NT.t('{n} with astrocytoma', { n: p.fam_astrocitoma }));
      if (p.fam_uveale) f.push(NT.t('{n} with uveal melanoma', { n: p.fam_uveale }));
      righe.push([NT.t('Family history'), f.length ? f.join('; ') : NT.t('no cases indicated')]);
    }
    if (p.test_genetico && p.test_genetico !== 'no') righe.push([NT.t('Genetic test already done'), lab(TEST_GEN, p.test_genetico)]);
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
      const dd = (prima.diametro_mm && ultima.diametro_mm) ? ' ' + NT.t('Diameter: from {da} to {a} mm.', { da: NT.num(prima.diametro_mm), a: NT.num(ultima.diametro_mm) }) : '';
      variazione = NT.t('{n} photos in {giorni} (from {da} to {a}).', { n: foto.length, giorni: NT.tp(giorni, '{n} day', '{n} days'), da: NT.fmtData(prima.scattata_il), a: NT.fmtData(ultima.scattata_il) }) + dd;
    }
    const mostra = foto.length <= 8 ? foto : [foto[0], foto[1]].concat(foto.slice(-6));
    return h('section', { class: 'st-neo' },
      h('h3', {}, h('span', { class: 'st-badge' }, num), ' ', n.nome, n.regione ? ' – ' + NT.tr(n.regione) : ' – ' + (n.vista === 'retro' ? NT.t('back') : NT.t('front'))),
      n.note ? h('p', { class: 'st-nota' }, NT.t('Notes:') + ' ' + n.note) : null,
      foto.length ? [
        variazione ? h('p', {}, variazione) : h('p', {}, prima.diametro_mm ? NT.t('1 photo from {data}, diameter {mm} mm.', { data: NT.fmtData(prima.scattata_il), mm: NT.num(prima.diametro_mm) }) : NT.t('1 photo from {data}.', { data: NT.fmtData(prima.scattata_il) })),
        h('div', { class: 'st-foto' }, mostra.map(f => h('figure', {}, h('img', { src: '/foto/' + f.id + '/mini?l=480', alt: NT.t('Photo from {data}', { data: NT.fmtData(f.scattata_il) }) }),
          h('figcaption', {}, NT.fmtData(f.scattata_il), f.diametro_mm ? ' · ' + NT.num(f.diametro_mm) + ' mm' : '', f.tipo === 'dermoscopica' ? ' · ' + NT.t('dermoscopic') : '')))),
        foto.length > mostra.length ? h('p', { class: 'st-nota' }, NT.t('Showing {n} photos out of {tot}.', { n: mostra.length, tot: foto.length })) : null,
        ultima.esito ? h('p', { class: 'st-nota' }, NT.t('Latest automatic analysis ({data}): {esito}. Research tool, not diagnostic.', { data: NT.fmtData(ultima.scattata_il), esito: ESITO_STAMPA[ultima.esito] || ultima.esito })) : null,
      ] : h('p', { class: 'st-nota' }, NT.t('No photo recorded yet.')));
  }

  NT.stampaNei = async function (ids) {
    if (!S.utente) return;
    const area = NT.$('#stampa');
    try {
      NT.toast(NT.t('Preparing the sheet…'), 'info');
      await NT.ricaricaUtente();
      await NT.ricaricaNei();
      const scelti = S.nei.filter(n => !n.archiviato && (!ids || ids.includes(n.id)));
      if (!scelti.length) { NT.toast(NT.t('There are no moles to print.'), 'errore'); return; }
      const dettagli = await Promise.all(scelti.map(n => NT.get('/api/nevi/' + n.id)));
      const tutti = S.nei.filter(n => !n.archiviato);
      const numero = id => tutti.findIndex(n => n.id === id) + 1;
      const u = S.utente, rischio = u.rischio.presenti;
      const prof = riepilogoProfilo(u);
      const nuovo = h('div', { class: 'st-pagina' },
        h('header', { class: 'st-testata' }, h('div', {}, h('h1', {}, NT.t('Mole sheet – {nome}', { nome: u.nome })), h('div', { class: 'st-sotto' }, NT.t('Printed on {data} with NeoTracker', { data: NT.fmtData(NT.oggiISO()) }))),
          h('div', { class: 'st-sotto' }, NT.tp(scelti.length, '{n} mole on this sheet', '{n} moles on this sheet'))),
        h('section', { class: 'st-profilo' }, h('h2', {}, NT.t('Personal details')),
          prof.length ? h('dl', {}, prof.map(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])) : h('p', { class: 'st-nota' }, NT.t('Profile not filled in.')),
          rischio.length ? h('p', {}, h('strong', {}, NT.t('Risk factors indicated:') + ' '), rischio.map(r => NT.tr(r.etichetta)).join('; ') + '.') : null),
        h('section', {}, h('h2', {}, NT.t('Where they are')), mappaStampa(scelti.map(n => Object.assign({}, n))),
          h('p', { class: 'st-nota' }, NT.t('The numbers match the following sheets. In the figure: the front view on the left, the back view on the right.'))),
        dettagli.map(d => schedaNeo(numero(d.nevo.id), d.nevo, d.foto)),
        h('footer', { class: 'st-avviso' }, NT.t('This sheet collects data entered by the person and photos taken by them. The results of the automatic analysis are experimental, are not a diagnosis and do not replace a dermatological visit or dermoscopy.')));
      // numbers consistent with the map: it uses the global numbering, not that of the selection
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
