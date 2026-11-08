/* ============================================================================
   v_scienza.js - letteratura scientifica (PubMed) e genetica del melanoma ereditario
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  const TIPI = {
    'Review': 'Revisione', 'Systematic Review': 'Revisione sistematica', 'Meta-Analysis': 'Meta-analisi',
    'Practice Guideline': 'Linea guida', 'Guideline': 'Linea guida', 'Consensus Development Conference': 'Consenso',
    'Randomized Controlled Trial': 'Studio randomizzato', 'Clinical Trial': 'Studio clinico', 'Observational Study': 'Studio osservazionale',
  };
  const fmtN = n => Number(n).toLocaleString('it-IT');

  function articolo(a) {
    const tipi = (a.tipi || []).map(t => TIPI[t]).filter(Boolean);
    return h('article', { class: 'articolo' },
      h('a', { href: a.url, target: '_blank', rel: 'noopener noreferrer', class: 'art-titolo' }, a.titolo || '(senza titolo)'),
      h('div', { class: 'art-meta' }, [a.autori, a.rivista, a.anno].filter(Boolean).join(' · ')),
      tipi.length ? h('div', { class: 'chips' }, [...new Set(tipi)].map(t => h('span', { class: 'chip chip-neutro' }, t))) : null,
      a.abstract ? h('details', { class: 'abstract' }, h('summary', {}, 'Leggi l\'abstract'), h('p', {}, a.abstract),
        h('div', { class: 'piccolo muted' }, 'In inglese · PubMed ', a.pmid, a.doi ? [' · ', NT.link('https://doi.org/' + a.doi, 'DOI')] : null)) : h('div', { class: 'piccolo muted' }, 'PubMed ' + a.pmid + ' · abstract non disponibile'));
  }

  function avvisoCache(d) {
    if (d.obsoleta) return h('div', { class: 'banda giallo' }, 'PubMed non è raggiungibile: mostro l\'ultima ricerca salvata il ' + d.data + '.');
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
        const corpo = h('div', { class: 'sez-corpo' }, h('div', { class: 'piccolo muted' }, 'Non ancora scansionata.'));
        const testa = h('h3', {}, s.titolo);
        const box = h('div', { class: 'sez' }, testa, corpo);
        sezioni.push({ id: s.id, titolo: s.titolo, corpo, testa });
        return box;
      });
      return h('section', { class: 'scheda' }, h('h2', {}, t.titolo), corpiSez);
    });

    const progresso = h('span', { class: 'piccolo muted' }, '');
    const btnScan = h('button', { class: 'btn btn-pri', onclick: () => scansiona(false) }, NT.icona('cerca', 18), 'Scansiona la letteratura');
    const btnForza = h('button', { class: 'btn', title: 'Rifà la ricerca ignorando i risultati salvati', onclick: () => scansiona(true) }, 'Aggiorna');

    async function scansiona(forza) {
      if (inCorso) return;
      inCorso = true; btnScan.disabled = true; btnForza.disabled = true;
      let n = 0;
      for (const s of sezioni) {
        if (!attivo) break;
        n++; progresso.textContent = 'Sezione ' + n + ' di ' + sezioni.length + '…';
        NT.riempi(s.corpo, NT.caricamento('Cerco su PubMed…'));
        try {
          const d = await NT.get('/api/letteratura/sezione?id=' + encodeURIComponent(s.id) + '&utente=' + uid + (forza ? '&forza=1' : ''));
          NT.riempi(s.corpo, avvisoCache(d),
            h('div', { class: 'piccolo muted spazio-giu' }, fmtN(d.conteggio) + ' articoli trovati su PubMed · ricerca del ' + d.data + (d.da_cache ? ' (salvata)' : '')),
            d.articoli.length ? d.articoli.map(articolo) : h('div', { class: 'piccolo muted' }, 'Nessun articolo trovato.'));
        } catch (e) { NT.riempi(s.corpo, h('div', { class: 'errore-campo' }, e.message)); }
      }
      inCorso = false;
      if (!attivo) return;
      btnScan.disabled = false; btnForza.disabled = false; progresso.textContent = 'Scansione completata.';
    }

    /* ricerca libera */
    const q = h('input', { type: 'search', class: 'campo', placeholder: 'Cerca altro (es. "ugly duckling sign", "nail melanoma"…)', maxlength: 200 });
    const risLibera = h('div', { class: 'ris-libera' });
    const cerca = async () => {
      if (q.value.trim().length < 3) { NT.toast('Scrivi almeno 3 caratteri.', 'errore'); return; }
      NT.riempi(risLibera, NT.caricamento('Cerco su PubMed…'));
      try {
        const d = await NT.get('/api/letteratura/cerca?q=' + encodeURIComponent(q.value));
        NT.riempi(risLibera, avvisoCache(d), h('div', { class: 'piccolo muted spazio-giu' }, fmtN(d.conteggio) + ' articoli su melanoma e «' + q.value.trim() + '»'),
          d.articoli.length ? d.articoli.map(articolo) : h('div', { class: 'piccolo muted' }, 'Nessun articolo trovato.'));
      } catch (e) { NT.riempi(risLibera, h('div', { class: 'errore-campo' }, e.message)); }
    };
    q.addEventListener('keydown', e => { if (e.key === 'Enter') cerca(); });

    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, 'Letteratura scientifica'),
      h('p', { class: 'lead' }, 'Articoli recenti e rilevanti su come riconoscere i nei sospetti, sull\'affidabilità di app e intelligenza artificiale e sul melanoma ereditario. I risultati arrivano da PubMed, la banca dati pubblica della National Library of Medicine (USA).'),
      h('div', { class: 'scheda azione-scan' }, h('div', { class: 'riga-inline' }, btnScan, btnForza, progresso),
        h('p', { class: 'piccolo muted' }, 'Le ricerche partono da questo computer verso PubMed (nessun dato personale viene inviato). I risultati si salvano per 7 giorni. ' +
          'Le sezioni «scelte per te» usano parole legate al tuo profilo (per esempio fototipo o numero di nei): se preferisci non inviarle, non scansionare quella sezione.'),
        h('div', { class: 'riga-inline' }, h('button', { class: 'btn-testo', onclick: () => NT.dialogoABCDE() }, 'Promemoria ABCDE per riconoscere un neo'))),
      h('div', { class: 'scheda' }, h('h2', {}, 'Cerca nella letteratura'), h('div', { class: 'riga-inline' }, q, h('button', { class: 'btn', onclick: cerca }, 'Cerca')), risLibera),
      temiEl,
      h('div', { class: 'scheda piccolo muted' }, 'PubMed è un servizio della National Library of Medicine. Gli abstract sono mostrati per consultazione personale, in inglese; per il testo completo apri l\'articolo sul sito della rivista. ',
        'Gli articoli sono scelti da una ricerca automatica e non sono stati valutati da NeoTracker: leggili con il tuo medico.')));
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
      h('span', { class: 'esito-criterio', 'aria-label': c.soddisfatto ? 'Soddisfatto' : 'Non soddisfatto' }, c.soddisfatto ? NT.icona('ok', 16) : '—'),
      h('div', {}, h('strong', {}, c.titolo), h('div', { class: 'piccolo muted' }, c.spiegazione), h('div', { class: 'piccolo muted' }, 'Fonte: ' + c.fonte)))));

    const righe = dati.geni.map(ge => {
      const risultato = h('div', { class: 'gene-ris' }, h('span', { class: 'piccolo muted' }, 'Non ancora scansionato'));
      return { nome: ge.gene, risultato, riga: h('tr', {}, h('td', {}, h('strong', {}, ge.gene), g.geni_suggeriti.includes(ge.gene) ? h('div', { class: 'chip chip-neutro' }, 'nel pannello') : null),
        h('td', {}, ge.rischio), h('td', {}, ge.ruolo, risultato)) };
    });
    const progresso = h('span', { class: 'piccolo muted' }, '');
    const btn = h('button', { class: 'btn btn-pri', onclick: () => scansiona(false) }, NT.icona('cerca', 18), 'Scansiona la letteratura sui geni');
    const btnF = h('button', { class: 'btn', onclick: () => scansiona(true) }, 'Aggiorna');
    async function scansiona(forza) {
      if (inCorso) return;
      inCorso = true; btn.disabled = true; btnF.disabled = true;
      let n = 0;
      for (const r of righe) {
        if (!attivo) break;
        n++; progresso.textContent = 'Gene ' + n + ' di ' + righe.length + ' (' + r.nome + ')…';
        NT.riempi(r.risultato, NT.caricamento('Cerco…'));
        try {
          const d = await NT.get('/api/genetica/gene?nome=' + encodeURIComponent(r.nome) + (forza ? '&forza=1' : ''));
          NT.riempi(r.risultato, h('div', { class: 'gene-conta' }, h('strong', {}, fmtN(d.conteggio)), ' studi su PubMed', d.obsoleta ? ' (ricerca salvata del ' + d.data + ')' : ''),
            d.articoli.length ? h('details', { class: 'abstract' }, h('summary', {}, 'Studi più pertinenti'), d.articoli.map(articolo)) : null);
        } catch (e) { NT.riempi(r.risultato, h('div', { class: 'errore-campo' }, e.message)); }
      }
      inCorso = false;
      if (attivo) { btn.disabled = false; btnF.disabled = false; progresso.textContent = 'Scansione completata.'; }
    }

    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, 'Melanoma ereditario e test genetico'),
      h('p', { class: 'lead' }, 'Circa il 5-10% dei melanomi si presenta in famiglie con una predisposizione ereditaria (Leachman 2009). Qui trovi i criteri che usano gli specialisti per decidere se proporre una consulenza genetica, i geni coinvolti e la letteratura su ciascuno.'),
      h('section', { class: 'scheda' }, h('h2', {}, 'I tuoi dati rispetto ai criteri'),
        h('div', { class: 'banda ' + cls }, g.messaggio),
        g.esito !== 'dati_insufficienti' ? criteri : null,
        h('div', { class: 'azioni sinistra' }, h('a', { class: 'btn', href: '#/profilo' }, g.esito === 'dati_insufficienti' ? 'Compila la familiarità nel Profilo' : 'Modifica i dati nel Profilo')),
        h('p', { class: 'piccolo muted' }, 'Criteri semplificati, a scopo informativo. Il test genetico riguarda una piccola minoranza di persone e non è un esame di routine: è lo specialista a decidere se e quale test proporre, di norma dopo una consulenza genetica e partendo, quando possibile, da un familiare che ha avuto la malattia.')),
      h('section', { class: 'scheda' }, h('h2', {}, 'Cosa sapere prima di un test genetico'),
        h('ul', { class: 'punti' },
          h('li', {}, 'Un risultato positivo indica un rischio più alto, non la certezza di ammalarsi; un risultato negativo non azzera il rischio (molte famiglie non hanno una variante identificabile).'),
          h('li', {}, 'Il risultato riguarda anche i familiari di sangue: per questo la consulenza prima e dopo il test è parte del percorso.'),
          h('li', {}, 'Le linee guida raccomandano il test solo dopo una selezione accurata dei candidati e un\'adeguata consulenza (Rossi 2019); l\'uso dei pannelli multigene è ancora discusso.'),
          h('li', {}, 'Con o senza test, per chi ha una storia familiare restano fondamentali la protezione dal sole, l\'autoesame della pelle e i controlli dermatologici periodici.'))),
      h('section', { class: 'scheda' }, h('h2', {}, 'I geni più studiati'),
        h('div', { class: 'azione-scan' }, h('div', { class: 'riga-inline' }, btn, btnF, progresso)),
        h('div', { class: 'tabella-scroll' }, h('table', { class: 'tabella' }, h('thead', {}, h('tr', {}, h('th', {}, 'Gene'), h('th', {}, 'Rischio associato'), h('th', {}, 'Ruolo e letteratura'))), h('tbody', {}, righe.map(r => r.riga))))),
      h('section', { class: 'scheda' }, h('h2', {}, 'Fonti'), h('ul', { class: 'fonti' }, dati.fonti.map(f => h('li', {}, NT.link(f.url, f.titolo)))),
        h('p', { class: 'piccolo muted' }, 'NeoTracker non è un servizio di consulenza genetica. Per una valutazione personale rivolgiti al dermatologo o a un centro di genetica oncologica.'))));
  };
})();
