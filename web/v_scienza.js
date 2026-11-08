/* ============================================================================
   v_scienza.js - letteratura scientifica (PubMed) e genetica del melanoma ereditario
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  const TIPI = {
    'Review': NT.t('Revisione'), 'Systematic Review': NT.t('Revisione sistematica'), 'Meta-Analysis': NT.t('Meta-analisi'),
    'Practice Guideline': NT.t('Linea guida'), 'Guideline': NT.t('Linea guida'), 'Consensus Development Conference': NT.t('Consenso'),
    'Randomized Controlled Trial': NT.t('Studio randomizzato'), 'Clinical Trial': NT.t('Studio clinico'), 'Observational Study': NT.t('Studio osservazionale'),
  };
  const fmtN = n => NT.migliaia(n);
  const dataRicerca = d => d.data_iso ? NT.fmtData(d.data_iso) : d.data;      // 'data_iso' manca nelle ricerche salvate da versioni vecchie

  function articolo(a) {
    const tipi = (a.tipi || []).map(t => TIPI[t]).filter(Boolean);
    return h('article', { class: 'articolo' },
      h('a', { href: a.url, target: '_blank', rel: 'noopener noreferrer', class: 'art-titolo' }, a.titolo || NT.t('(senza titolo)')),
      h('div', { class: 'art-meta' }, [a.autori, a.rivista, a.anno].filter(Boolean).join(' · ')),
      tipi.length ? h('div', { class: 'chips' }, [...new Set(tipi)].map(t => h('span', { class: 'chip chip-neutro' }, t))) : null,
      a.abstract ? h('details', { class: 'abstract' }, h('summary', {}, NT.t('Leggi l\'abstract')), h('p', {}, a.abstract),
        h('div', { class: 'piccolo muted' }, NT.t('In inglese') + ' · PubMed ', a.pmid, a.doi ? [' · ', NT.link('https://doi.org/' + a.doi, 'DOI')] : null)) : h('div', { class: 'piccolo muted' }, NT.t('PubMed {pmid} · abstract non disponibile', { pmid: a.pmid })));
  }

  function avvisoCache(d) {
    if (d.obsoleta) return h('div', { class: 'banda giallo' }, NT.t('PubMed non è raggiungibile: mostro l\'ultima ricerca salvata il {data}.', { data: dataRicerca(d) }));
    return null;
  }

  /* ============================== LETTERATURA ============================== */
  NT.viste.letteratura = async function (cont) {
    const uid = S.utente ? S.utente.id : 0;
    const temi = await NT.get('/api/letteratura/temi?utente=' + uid);
    let attivo = true, inCorso = false;
    NT.alCambioPagina(() => { attivo = false; });

    const sezioni = [];     // { id, titolo, corpo, stato }
    const temiEl = temi.map(t => {
      const corpiSez = t.sezioni.map(s => {
        const corpo = h('div', { class: 'sez-corpo' }, h('div', { class: 'piccolo muted' }, NT.t('Non ancora scansionata.')));
        const testa = h('h3', {}, NT.tr(s.titolo));
        const box = h('div', { class: 'sez' }, testa, corpo);
        sezioni.push({ id: s.id, titolo: s.titolo, corpo, testa });
        return box;
      });
      return h('section', { class: 'scheda' }, h('h2', {}, NT.tr(t.titolo)), corpiSez);
    });

    const progresso = h('span', { class: 'piccolo muted' }, '');
    const btnScan = h('button', { class: 'btn btn-pri', onclick: () => scansiona(false) }, NT.icona('cerca', 18), NT.t('Scansiona la letteratura'));
    const btnForza = h('button', { class: 'btn', title: NT.t('Rifà la ricerca ignorando i risultati salvati'), onclick: () => scansiona(true) }, NT.t('Aggiorna'));

    async function scansiona(forza) {
      if (inCorso) return;
      inCorso = true; btnScan.disabled = true; btnForza.disabled = true;
      let n = 0;
      for (const s of sezioni) {
        if (!attivo) break;
        n++; progresso.textContent = NT.t('Sezione {n} di {tot}…', { n: n, tot: sezioni.length });
        NT.riempi(s.corpo, NT.caricamento(NT.t('Cerco su PubMed…')));
        try {
          const d = await NT.get('/api/letteratura/sezione?id=' + encodeURIComponent(s.id) + '&utente=' + uid + (forza ? '&forza=1' : ''));
          NT.riempi(s.corpo, avvisoCache(d),
            h('div', { class: 'piccolo muted spazio-giu' }, (d.da_cache ? NT.t('{n} articoli trovati su PubMed · ricerca del {data} (salvata)', { n: fmtN(d.conteggio), data: dataRicerca(d) })
              : NT.t('{n} articoli trovati su PubMed · ricerca del {data}', { n: fmtN(d.conteggio), data: dataRicerca(d) }))),
            d.articoli.length ? d.articoli.map(articolo) : h('div', { class: 'piccolo muted' }, NT.t('Nessun articolo trovato.')));
        } catch (e) { NT.riempi(s.corpo, h('div', { class: 'errore-campo' }, e.message)); }
      }
      inCorso = false;
      if (!attivo) return;
      btnScan.disabled = false; btnForza.disabled = false; progresso.textContent = NT.t('Scansione completata.');
    }

    /* ricerca libera */
    const q = h('input', { type: 'search', class: 'campo', placeholder: NT.t('Cerca altro (es. "ugly duckling sign", "nail melanoma"…)'), maxlength: 200 });
    const risLibera = h('div', { class: 'ris-libera' });
    const cerca = async () => {
      if (q.value.trim().length < 3) { NT.toast(NT.t('Scrivi almeno 3 caratteri.'), 'errore'); return; }
      NT.riempi(risLibera, NT.caricamento(NT.t('Cerco su PubMed…')));
      try {
        const d = await NT.get('/api/letteratura/cerca?q=' + encodeURIComponent(q.value));
        NT.riempi(risLibera, avvisoCache(d), h('div', { class: 'piccolo muted spazio-giu' }, NT.t('{n} articoli su melanoma e «{termine}»', { n: fmtN(d.conteggio), termine: q.value.trim() })),
          d.articoli.length ? d.articoli.map(articolo) : h('div', { class: 'piccolo muted' }, NT.t('Nessun articolo trovato.')));
      } catch (e) { NT.riempi(risLibera, h('div', { class: 'errore-campo' }, e.message)); }
    };
    q.addEventListener('keydown', e => { if (e.key === 'Enter') cerca(); });

    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, NT.t('Letteratura scientifica')),
      h('p', { class: 'lead' }, NT.t('Articoli recenti e rilevanti su come riconoscere i nei sospetti, sull\'affidabilità di app e intelligenza artificiale e sul melanoma ereditario. I risultati arrivano da PubMed, la banca dati pubblica della National Library of Medicine (USA).')),
      h('div', { class: 'scheda azione-scan' }, h('div', { class: 'riga-inline' }, btnScan, btnForza, progresso),
        h('p', { class: 'piccolo muted' }, NT.t('Le ricerche partono da questo computer verso PubMed (nessun dato personale viene inviato). I risultati si salvano per 7 giorni.') + ' ' +
          NT.t('Le sezioni «scelte per te» usano parole legate al tuo profilo (per esempio fototipo o numero di nei): se preferisci non inviarle, non scansionare quella sezione.')),
        h('div', { class: 'riga-inline' }, h('button', { class: 'btn-testo', onclick: () => NT.dialogoABCDE() }, NT.t('Promemoria ABCDE per riconoscere un neo')))),
      h('div', { class: 'scheda' }, h('h2', {}, NT.t('Cerca nella letteratura')), h('div', { class: 'riga-inline' }, q, h('button', { class: 'btn', onclick: cerca }, NT.t('Cerca'))), risLibera),
      temiEl,
      h('div', { class: 'scheda piccolo muted' }, NT.t('PubMed è un servizio della National Library of Medicine. Gli abstract sono mostrati per consultazione personale, in inglese; per il testo completo apri l\'articolo sul sito della rivista.') + ' ',
        NT.t('Gli articoli sono scelti da una ricerca automatica e non sono stati valutati da NeoTracker: leggili con il tuo medico.'))));
  };

  /* ================================ GENETICA ================================ */
  NT.viste.genetica = async function (cont) {
    await NT.ricaricaUtente();
    const g = S.utente.genetica;
    const dati = await NT.get('/api/genetica/geni');
    let attivo = true, inCorso = false;
    NT.alCambioPagina(() => { attivo = false; });

    const cls = { criteri_soddisfatti: 'arancio', nessun_criterio: 'neutro', dati_insufficienti: 'giallo' }[g.esito];
    const criteri = h('ul', { class: 'criteri' }, g.criteri.map(c => h('li', { class: c.soddisfatto ? 'si' : 'no' },
      h('span', { class: 'esito-criterio', 'aria-label': c.soddisfatto ? NT.t('Soddisfatto') : NT.t('Non soddisfatto') }, c.soddisfatto ? NT.icona('ok', 16) : '—'),
      h('div', {}, h('strong', {}, NT.tr(c.titolo)), h('div', { class: 'piccolo muted' }, NT.tr(c.spiegazione)), h('div', { class: 'piccolo muted' }, NT.t('Fonte:') + ' ' + NT.tr(c.fonte))))));

    const righe = dati.geni.map(ge => {
      const risultato = h('div', { class: 'gene-ris' }, h('span', { class: 'piccolo muted' }, NT.t('Non ancora scansionato')));
      return { nome: ge.gene, risultato, riga: h('tr', {}, h('td', {}, h('strong', {}, ge.gene), g.geni_suggeriti.includes(ge.gene) ? h('div', { class: 'chip chip-neutro' }, NT.t('nel pannello')) : null),
        h('td', {}, NT.tr(ge.rischio)), h('td', {}, NT.tr(ge.ruolo), risultato)) };
    });
    const progresso = h('span', { class: 'piccolo muted' }, '');
    const btn = h('button', { class: 'btn btn-pri', onclick: () => scansiona(false) }, NT.icona('cerca', 18), NT.t('Scansiona la letteratura sui geni'));
    const btnF = h('button', { class: 'btn', onclick: () => scansiona(true) }, NT.t('Aggiorna'));
    async function scansiona(forza) {
      if (inCorso) return;
      inCorso = true; btn.disabled = true; btnF.disabled = true;
      let n = 0;
      for (const r of righe) {
        if (!attivo) break;
        n++; progresso.textContent = NT.t('Gene {n} di {tot} ({nome})…', { n: n, tot: righe.length, nome: r.nome });
        NT.riempi(r.risultato, NT.caricamento(NT.t('Cerco…')));
        try {
          const d = await NT.get('/api/genetica/gene?nome=' + encodeURIComponent(r.nome) + (forza ? '&forza=1' : ''));
          NT.riempi(r.risultato, h('div', { class: 'gene-conta' }, h('strong', {}, fmtN(d.conteggio)), ' ' + NT.t('studi su PubMed'), d.obsoleta ? ' ' + NT.t('(ricerca salvata del {data})', { data: dataRicerca(d) }) : ''),
            d.articoli.length ? h('details', { class: 'abstract' }, h('summary', {}, NT.t('Studi più pertinenti')), d.articoli.map(articolo)) : null);
        } catch (e) { NT.riempi(r.risultato, h('div', { class: 'errore-campo' }, e.message)); }
      }
      inCorso = false;
      if (attivo) { btn.disabled = false; btnF.disabled = false; progresso.textContent = NT.t('Scansione completata.'); }
    }

    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, NT.t('Melanoma ereditario e test genetico')),
      h('p', { class: 'lead' }, NT.t('Circa il 5-10% dei melanomi si presenta in famiglie con una predisposizione ereditaria (Leachman 2009). Qui trovi i criteri che usano gli specialisti per decidere se proporre una consulenza genetica, i geni coinvolti e la letteratura su ciascuno.')),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('I tuoi dati rispetto ai criteri')),
        h('div', { class: 'banda ' + cls }, NT.tr(g.messaggio) + (g.messaggio_aggiunta ? ' ' + NT.tr(g.messaggio_aggiunta) : '')),
        g.esito !== 'dati_insufficienti' ? criteri : null,
        h('div', { class: 'azioni sinistra' }, h('a', { class: 'btn', href: '#/profilo' }, g.esito === 'dati_insufficienti' ? NT.t('Compila la familiarità nel Profilo') : NT.t('Modifica i dati nel Profilo'))),
        h('p', { class: 'piccolo muted' }, NT.t('Criteri semplificati, a scopo informativo. Il test genetico riguarda una piccola minoranza di persone e non è un esame di routine: è lo specialista a decidere se e quale test proporre, di norma dopo una consulenza genetica e partendo, quando possibile, da un familiare che ha avuto la malattia.'))),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('Cosa sapere prima di un test genetico')),
        h('ul', { class: 'punti' },
          h('li', {}, NT.t('Un risultato positivo indica un rischio più alto, non la certezza di ammalarsi; un risultato negativo non azzera il rischio (molte famiglie non hanno una variante identificabile).')),
          h('li', {}, NT.t('Il risultato riguarda anche i familiari di sangue: per questo la consulenza prima e dopo il test è parte del percorso.')),
          h('li', {}, NT.t('Le linee guida raccomandano il test solo dopo una selezione accurata dei candidati e un\'adeguata consulenza (Rossi 2019); l\'uso dei pannelli multigene è ancora discusso.')),
          h('li', {}, NT.t('Con o senza test, per chi ha una storia familiare restano fondamentali la protezione dal sole, l\'autoesame della pelle e i controlli dermatologici periodici.')))),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('I geni più studiati')),
        h('div', { class: 'azione-scan' }, h('div', { class: 'riga-inline' }, btn, btnF, progresso)),
        h('div', { class: 'tabella-scroll' }, h('table', { class: 'tabella' }, h('thead', {}, h('tr', {}, h('th', {}, NT.t('Gene')), h('th', {}, NT.t('Rischio associato')), h('th', {}, NT.t('Ruolo e letteratura')))), h('tbody', {}, righe.map(r => r.riga))))),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('Fonti')), h('ul', { class: 'fonti' }, dati.fonti.map(f => h('li', {}, NT.link(f.url, NT.tr(f.titolo))))),
        h('p', { class: 'piccolo muted' }, NT.t('NeoTracker non è un servizio di consulenza genetica. Per una valutazione personale rivolgiti al dermatologo o a un centro di genetica oncologica.')))));
  };
})();
