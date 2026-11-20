/* ============================================================================
   v_scienza.js - scientific literature (PubMed) and genetics of hereditary melanoma
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  const TIPI = {
    'Review': NT.t('Review'), 'Systematic Review': NT.t('Systematic review'), 'Meta-Analysis': NT.t('Meta-analysis'),
    'Practice Guideline': NT.t('Guideline'), 'Guideline': NT.t('Guideline'), 'Consensus Development Conference': NT.t('Consent'),
    'Randomized Controlled Trial': NT.t('Randomised trial'), 'Clinical Trial': NT.t('Clinical trial'), 'Observational Study': NT.t('Observational study'),
  };
  const fmtN = n => NT.migliaia(n);
  const dataRicerca = d => d.data_iso ? NT.fmtData(d.data_iso) : d.data;      // 'data_iso' is missing in searches saved by old versions

  function articolo(a) {
    const tipi = (a.tipi || []).map(t => TIPI[t]).filter(Boolean);
    return h('article', { class: 'articolo' },
      h('a', { href: a.url, target: '_blank', rel: 'noopener noreferrer', class: 'art-titolo' }, a.titolo || NT.t('(untitled)')),
      h('div', { class: 'art-meta' }, [a.autori, a.rivista, a.anno].filter(Boolean).join(' · ')),
      tipi.length ? h('div', { class: 'chips' }, [...new Set(tipi)].map(t => h('span', { class: 'chip chip-neutro' }, t))) : null,
      a.abstract ? h('details', { class: 'abstract' }, h('summary', {}, NT.t('Read the abstract')), h('p', {}, a.abstract),
        h('div', { class: 'piccolo muted' }, NT.t('In English') + ' · PubMed ', a.pmid, a.doi ? [' · ', NT.link('https://doi.org/' + a.doi, 'DOI')] : null)) : h('div', { class: 'piccolo muted' }, NT.t('PubMed {pmid} · abstract not available', { pmid: a.pmid })));
  }

  function avvisoCache(d) {
    if (d.obsoleta) return h('div', { class: 'banda giallo' }, NT.t('PubMed is unreachable: showing the last saved search from {data}.', { data: dataRicerca(d) }));
    return null;
  }

  /* ============================== LITERATURE ============================== */
  NT.viste.letteratura = async function (cont) {
    const uid = S.utente ? S.utente.id : 0;
    const temi = await NT.get('/api/letteratura/temi?utente=' + uid);
    let attivo = true, inCorso = false;
    NT.alCambioPagina(() => { attivo = false; });

    const sezioni = [];     // { id, titolo, corpo, stato }
    const temiEl = temi.map(t => {
      const corpiSez = t.sezioni.map(s => {
        const corpo = h('div', { class: 'sez-corpo' }, h('div', { class: 'piccolo muted' }, NT.t('Not scanned yet.')));
        const testa = h('h3', {}, NT.tr(s.titolo));
        const box = h('div', { class: 'sez' }, testa, corpo);
        sezioni.push({ id: s.id, titolo: s.titolo, corpo, testa });
        return box;
      });
      return h('section', { class: 'scheda' }, h('h2', {}, NT.tr(t.titolo)), corpiSez);
    });

    const progresso = h('span', { class: 'piccolo muted' }, '');
    const btnScan = h('button', { class: 'btn btn-pri', onclick: () => scansiona(false) }, NT.icona('cerca', 18), NT.t('Scan the literature'));
    const btnForza = h('button', { class: 'btn', title: NT.t('Repeat the search ignoring the saved results'), onclick: () => scansiona(true) }, NT.t('Refresh'));

    async function scansiona(forza) {
      if (inCorso) return;
      inCorso = true; btnScan.disabled = true; btnForza.disabled = true;
      let n = 0;
      for (const s of sezioni) {
        if (!attivo) break;
        n++; progresso.textContent = NT.t('Section {n} of {tot}…', { n: n, tot: sezioni.length });
        NT.riempi(s.corpo, NT.caricamento(NT.t('Searching PubMed…')));
        try {
          const d = await NT.get('/api/letteratura/sezione?id=' + encodeURIComponent(s.id) + '&utente=' + uid + (forza ? '&forza=1' : ''));
          NT.riempi(s.corpo, avvisoCache(d),
            h('div', { class: 'piccolo muted spazio-giu' }, (d.da_cache ? NT.t('{n} articles found on PubMed · search of {data} (saved)', { n: fmtN(d.conteggio), data: dataRicerca(d) })
              : NT.t('{n} articles found on PubMed · search of {data}', { n: fmtN(d.conteggio), data: dataRicerca(d) }))),
            d.articoli.length ? d.articoli.map(articolo) : h('div', { class: 'piccolo muted' }, NT.t('No articles found.')));
        } catch (e) { NT.riempi(s.corpo, h('div', { class: 'errore-campo' }, e.message)); }
      }
      inCorso = false;
      if (!attivo) return;
      btnScan.disabled = false; btnForza.disabled = false; progresso.textContent = NT.t('Scan complete.');
    }

    /* free search */
    const q = h('input', { type: 'search', class: 'campo', placeholder: NT.t('Search for more (e.g. "ugly duckling sign", "nail melanoma"…)'), maxlength: 200 });
    const risLibera = h('div', { class: 'ris-libera' });
    const cerca = async () => {
      if (q.value.trim().length < 3) { NT.toast(NT.t('Type at least 3 characters.'), 'errore'); return; }
      NT.riempi(risLibera, NT.caricamento(NT.t('Searching PubMed…')));
      try {
        const d = await NT.get('/api/letteratura/cerca?q=' + encodeURIComponent(q.value));
        NT.riempi(risLibera, avvisoCache(d), h('div', { class: 'piccolo muted spazio-giu' }, NT.t('{n} articles on melanoma and «{termine}»', { n: fmtN(d.conteggio), termine: q.value.trim() })),
          d.articoli.length ? d.articoli.map(articolo) : h('div', { class: 'piccolo muted' }, NT.t('No articles found.')));
      } catch (e) { NT.riempi(risLibera, h('div', { class: 'errore-campo' }, e.message)); }
    };
    q.addEventListener('keydown', e => { if (e.key === 'Enter') cerca(); });

    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, NT.t('Scientific literature')),
      h('p', { class: 'lead' }, NT.t('Recent, relevant articles on recognising suspicious moles, on the reliability of apps and artificial intelligence, and on hereditary melanoma. Results come from PubMed, the public database of the National Library of Medicine (USA).')),
      h('div', { class: 'scheda azione-scan' }, h('div', { class: 'riga-inline' }, btnScan, btnForza, progresso),
        h('p', { class: 'piccolo muted' }, NT.t('Searches go from this computer to PubMed (no personal data is sent). Results are saved for 7 days.') + ' ' +
          NT.t('The «picked for you» sections use words linked to your profile (for example phototype or number of moles): if you prefer not to send them, do not scan that section.')),
        h('div', { class: 'riga-inline' }, h('button', { class: 'btn-testo', onclick: () => NT.dialogoABCDE() }, NT.t('ABCDE reminder for recognising a mole')))),
      h('div', { class: 'scheda' }, h('h2', {}, NT.t('Search the literature')), h('div', { class: 'riga-inline' }, q, h('button', { class: 'btn', onclick: cerca }, NT.t('Search'))), risLibera),
      temiEl,
      h('div', { class: 'scheda piccolo muted' }, NT.t("PubMed is a service of the National Library of Medicine. Abstracts are shown for personal consultation, in English; for the full text, open the article on the journal's website.") + ' ',
        NT.t('The articles are chosen by an automatic search and have not been assessed by NeoTracker: read them with your doctor.'))));
  };

  /* ================================ GENETICS ================================ */
  NT.viste.genetica = async function (cont) {
    await NT.ricaricaUtente();
    const g = S.utente.genetica;
    const dati = await NT.get('/api/genetica/geni');
    let attivo = true, inCorso = false;
    NT.alCambioPagina(() => { attivo = false; });

    const cls = { criteri_soddisfatti: 'arancio', nessun_criterio: 'neutro', dati_insufficienti: 'giallo' }[g.esito];
    const criteri = h('ul', { class: 'criteri' }, g.criteri.map(c => h('li', { class: c.soddisfatto ? 'si' : 'no' },
      h('span', { class: 'esito-criterio', 'aria-label': c.soddisfatto ? NT.t('Met') : NT.t('Not met') }, c.soddisfatto ? NT.icona('ok', 16) : '—'),
      h('div', {}, h('strong', {}, NT.tr(c.titolo)), h('div', { class: 'piccolo muted' }, NT.tr(c.spiegazione)), h('div', { class: 'piccolo muted' }, NT.t('Source:') + ' ' + NT.tr(c.fonte))))));

    const righe = dati.geni.map(ge => {
      const risultato = h('div', { class: 'gene-ris' }, h('span', { class: 'piccolo muted' }, NT.t('Not scanned yet')));
      return { nome: ge.gene, risultato, riga: h('tr', {}, h('td', {}, h('strong', {}, ge.gene), g.geni_suggeriti.includes(ge.gene) ? h('div', { class: 'chip chip-neutro' }, NT.t('in the panel')) : null),
        h('td', {}, NT.tr(ge.rischio)), h('td', {}, NT.tr(ge.ruolo), risultato)) };
    });
    const progresso = h('span', { class: 'piccolo muted' }, '');
    const btn = h('button', { class: 'btn btn-pri', onclick: () => scansiona(false) }, NT.icona('cerca', 18), NT.t('Scan the literature on genes'));
    const btnF = h('button', { class: 'btn', onclick: () => scansiona(true) }, NT.t('Refresh'));
    async function scansiona(forza) {
      if (inCorso) return;
      inCorso = true; btn.disabled = true; btnF.disabled = true;
      let n = 0;
      for (const r of righe) {
        if (!attivo) break;
        n++; progresso.textContent = NT.t('Gene {n} of {tot} ({nome})…', { n: n, tot: righe.length, nome: r.nome });
        NT.riempi(r.risultato, NT.caricamento(NT.t('Searching…')));
        try {
          const d = await NT.get('/api/genetica/gene?nome=' + encodeURIComponent(r.nome) + (forza ? '&forza=1' : ''));
          NT.riempi(r.risultato, h('div', { class: 'gene-conta' }, h('strong', {}, fmtN(d.conteggio)), ' ' + NT.t('studies on PubMed'), d.obsoleta ? ' ' + NT.t('(saved search from {data})', { data: dataRicerca(d) }) : ''),
            d.articoli.length ? h('details', { class: 'abstract' }, h('summary', {}, NT.t('Most relevant studies')), d.articoli.map(articolo)) : null);
        } catch (e) { NT.riempi(r.risultato, h('div', { class: 'errore-campo' }, e.message)); }
      }
      inCorso = false;
      if (attivo) { btn.disabled = false; btnF.disabled = false; progresso.textContent = NT.t('Scan complete.'); }
    }

    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, NT.t('Hereditary melanoma and genetic testing')),
      h('p', { class: 'lead' }, NT.t('About 5–10% of melanomas occur in families with an inherited predisposition (Leachman 2009). Here you find the criteria specialists use to decide whether to suggest genetic counselling, the genes involved and the literature on each.')),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('Your data against the criteria')),
        h('div', { class: 'banda ' + cls }, NT.tr(g.messaggio) + (g.messaggio_aggiunta ? ' ' + NT.tr(g.messaggio_aggiunta) : '')),
        g.esito !== 'dati_insufficienti' ? criteri : null,
        h('div', { class: 'azioni sinistra' }, h('a', { class: 'btn', href: '#/profilo' }, g.esito === 'dati_insufficienti' ? NT.t('Fill in the family history in your Profile') : NT.t('Edit the data in the Profile'))),
        h('p', { class: 'piccolo muted' }, NT.t('Simplified criteria, for information only. Genetic testing concerns a small minority of people and is not a routine examination: it is up to the specialist to decide whether and which test to offer, usually after genetic counselling and, when possible, starting from a relative who has had the disease.'))),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('What to know before a genetic test')),
        h('ul', { class: 'punti' },
          h('li', {}, NT.t('A positive result indicates a higher risk, not certainty of becoming ill; a negative result does not remove the risk (many families have no identifiable variant).')),
          h('li', {}, NT.t('The result also concerns blood relatives: that is why counselling before and after the test is part of the process.')),
          h('li', {}, NT.t('Guidelines recommend the test only after careful selection of candidates and adequate counselling (Rossi 2019); the use of multigene panels is still debated.')),
          h('li', {}, NT.t('With or without a test, for people with a family history, sun protection, skin self-examination and regular dermatological check-ups remain essential.')))),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('The most studied genes')),
        h('div', { class: 'azione-scan' }, h('div', { class: 'riga-inline' }, btn, btnF, progresso)),
        h('div', { class: 'tabella-scroll' }, h('table', { class: 'tabella' }, h('thead', {}, h('tr', {}, h('th', {}, NT.t('Gene')), h('th', {}, NT.t('Associated risk')), h('th', {}, NT.t('Role and literature')))), h('tbody', {}, righe.map(r => r.riga))))),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('Sources')), h('ul', { class: 'fonti' }, dati.fonti.map(f => h('li', {}, NT.link(f.url, NT.tr(f.titolo))))),
        h('p', { class: 'piccolo muted' }, NT.t('NeoTracker is not a genetic counselling service. For a personal assessment, see your dermatologist or an oncological genetics centre.')))));
  };
})();
