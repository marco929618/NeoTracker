/* ============================================================================
   v_profilo.js - fenotipo, storia personale e familiarità (si salva da solo)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  const FOTOTIPI = [
    [1, 'I', NT.t('Pelle molto chiara. Scotta sempre, non si abbronza mai (spesso capelli rossi, lentiggini).')],
    [2, 'II', NT.t('Pelle chiara. Scotta facilmente, si abbronza poco.')],
    [3, 'III', NT.t('Pelle chiara-olivastra. Scotta a volte, si abbronza gradualmente.')],
    [4, 'IV', NT.t('Pelle olivastra. Scotta poco, si abbronza facilmente.')],
    [5, 'V', NT.t('Pelle scura. Scotta raramente.')],
    [6, 'VI', NT.t('Pelle molto scura. Non scotta.')],
  ];

  NT.viste.profilo = async function (cont) {
    const u = S.utente;
    let p = Object.assign({}, u.profilo);
    let daSalvare = false;                // true tra una modifica e il salvataggio automatico
    const stato = h('span', { class: 'salvataggio' }, '');
    const riepilogo = h('aside', { class: 'riepilogo-profilo' });

    /* ---------- salvataggio automatico ---------- */
    const salvaOra = async () => {
      daSalvare = false;
      stato.textContent = NT.t('Salvataggio…'); stato.className = 'salvataggio';
      try {
        const r = await NT.api('PUT', '/api/utenti/' + u.id + '/profilo', p);
        S.utente = Object.assign(S.utente, r);
        stato.textContent = NT.t('Salvato ✓'); stato.className = 'salvataggio ok';
        disegnaRiepilogo();
      } catch (e) { stato.textContent = ''; NT.errore(e); }
    };
    const salva = NT.debounce(salvaOra, 700);
    const cambia = (campo, valore) => { p[campo] = valore; daSalvare = true; stato.textContent = NT.t('Modifiche non salvate…'); stato.className = 'salvataggio'; salva(); };
    NT.alCambioPagina(() => { if (daSalvare) salvaOra(); });

    /* ---------- piccoli componenti ---------- */
    const gruppo = (campo, opzioni, nome) => {
      const bottoni = opzioni.map(([val, testo]) => {
        const b = h('button', { type: 'button', class: 'pillola' + (p[campo] === val ? ' sel' : ''), 'aria-pressed': p[campo] === val ? 'true' : 'false',
          onclick: () => { p[campo] = (p[campo] === val && val !== '') ? '' : val; bottoni.forEach(x => { const on = x.dataset.v === p[campo]; x.classList.toggle('sel', on); x.setAttribute('aria-pressed', on ? 'true' : 'false'); }); cambia(campo, p[campo]); },
          dataset: { v: val } }, testo);
        return b;
      });
      return h('div', { class: 'campo-gruppo', role: 'group', 'aria-label': nome }, bottoni);
    };
    const campo = (titolo, contenuto, aiuto) => h('div', { class: 'campo-blocco' }, h('div', { class: 'campo-titolo' }, titolo), contenuto, aiuto ? h('div', { class: 'piccolo muted' }, aiuto) : null);
    const spunta = (c, testo) => h('label', { class: 'spunta' }, h('input', { type: 'checkbox', checked: !!p[c], onchange: ev => cambia(c, ev.target.checked) }), ' ' + testo);
    const contatore = (c, testo, aiuto) => {
      const val = h('output', { class: 'cont-val' }, String(p[c] || 0));
      const agg = d => { p[c] = Math.max(0, Math.min(20, (p[c] || 0) + d)); val.textContent = String(p[c]); if (c.startsWith('fam_') && !p.fam_compilata) { p.fam_compilata = true; const ck = NT.$('#ck-fam'); if (ck) ck.checked = true; } cambia(c, p[c]); };
      return h('div', { class: 'contatore-riga' }, h('div', {}, h('div', { class: 'campo-titolo' }, testo), aiuto ? h('div', { class: 'piccolo muted' }, aiuto) : null),
        h('div', { class: 'contatore' }, h('button', { type: 'button', class: 'btn-icona', 'aria-label': NT.t('Diminuisci: {voce}', { voce: testo }), onclick: () => agg(-1) }, NT.icona('meno', 16)), val,
          h('button', { type: 'button', class: 'btn-icona', 'aria-label': NT.t('Aumenta: {voce}', { voce: testo }), onclick: () => agg(1) }, NT.icona('piu', 16))));
    };

    /* ---------- fototipo ---------- */
    const COL = window.Corpo.colorePelle;
    const fototipi = h('div', { class: 'fototipi', role: 'radiogroup', 'aria-label': NT.t('Fototipo') }, FOTOTIPI.map(([n, r, d]) => h('button', { type: 'button', role: 'radio', class: 'fototipo' + (p.fototipo === n ? ' sel' : ''),
      'aria-checked': p.fototipo === n ? 'true' : 'false', dataset: { n: String(n) },
      onclick: () => { p.fototipo = p.fototipo === n ? 0 : n; NT.$$('.fototipo', fototipi).forEach(b => { const on = +b.dataset.n === p.fototipo; b.classList.toggle('sel', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); }); cambia('fototipo', p.fototipo); } },
      h('span', { class: 'swatch', style: { background: COL(n) } }), h('span', {}, h('strong', {}, NT.t('Tipo {n}', { n: r })), h('small', {}, d)))));

    const eta = h('span', { class: 'eta-calcolata' }, '');
    const aggiornaEta = () => {
      if (!p.data_nascita) { eta.textContent = ''; return; }
      const n = new Date(p.data_nascita + 'T12:00:00'), o = new Date();
      let a = o.getFullYear() - n.getFullYear(); if (o < new Date(o.getFullYear(), n.getMonth(), n.getDate())) a--;
      eta.textContent = a >= 0 ? NT.tp(a, '{n} anno', '{n} anni') : '';
    };
    const nascita = h('input', { type: 'date', class: 'campo corto', value: p.data_nascita || '', min: '1900-01-01', max: NT.oggiISO(),
      onchange: ev => { cambia('data_nascita', ev.target.value); aggiornaEta(); } });
    aggiornaEta();

    const sezione = (titolo, intro, ...figli) => h('section', { class: 'scheda' }, h('h2', {}, titolo), intro ? h('p', { class: 'piccolo muted' }, intro) : null, ...figli);

    /* ---------- immagine personale ---------- */
    const boxAvatar = h('div', { class: 'avatar-editor' });
    const entrata = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/bmp', hidden: true, 'aria-label': NT.t('Scegli un\'immagine personale') });
    const aggiornaAvatar = v => { S.utente.avatar_v = v; disegnaAvatar(); NT.ridisegnaTestata(); disegnaRiepilogo(); };
    async function scegliAvatar() {
      const file = entrata.files && entrata.files[0];
      entrata.value = '';
      if (!file) return;
      try {
        if (file.size > 40 * 1024 * 1024) throw new Error(NT.t('Il file è troppo grande (massimo 40 MB).'));
        const blob = await NT.ridimensionaQuadrato(file, 256);      // ritaglio quadrato al centro + riduzione, nel browser
        const r = await NT.api('POST', '/api/utenti/' + u.id + '/avatar', null, { raw: blob, tipo: 'image/jpeg' });
        aggiornaAvatar(r.avatar_v);
        NT.toast(NT.t('Immagine personale salvata.'), 'ok');
      } catch (e) { NT.errore(e); }
    }
    async function togliAvatar() {
      try { const r = await NT.api('DELETE', '/api/utenti/' + u.id + '/avatar'); aggiornaAvatar(r.avatar_v); NT.toast(NT.t('Immagine rimossa.'), 'ok'); }
      catch (e) { NT.errore(e); }
    }
    entrata.addEventListener('change', scegliAvatar);
    function disegnaAvatar() {
      NT.riempi(boxAvatar, NT.avatar(u.nome, 88, S.utente),
        h('div', { class: 'avatar-azioni' },
          h('p', { class: 'piccolo muted' }, NT.t('Puoi usare una tua foto, un disegno o un\'icona. L\'immagine viene ritagliata a quadrato e ridotta, resta solo su questo computer e non viene mai usata per l\'analisi dei nei.')),
          h('div', { class: 'riga-inline' },
            h('button', { type: 'button', class: 'btn', onclick: () => entrata.click() }, S.utente.avatar_v ? NT.t('Cambia immagine…') : NT.t('Scegli immagine…')),
            S.utente.avatar_v ? h('button', { type: 'button', class: 'btn-testo pericolo', onclick: togliAvatar }, NT.t('Rimuovi')) : null)));
    }
    disegnaAvatar();

    const form = h('div', { class: 'pila' },
      h('div', { class: 'scheda info' }, h('strong', {}, NT.t('A che cosa servono questi dati?') + ' '),
        NT.t('Non cambiano il risultato delle reti neurali, che guardano solo i pixel della foto. Servono a: (1) dare un contesto al rischio, (2) scegliere la letteratura scientifica adatta a te, (3) verificare i criteri per la consulenza genetica, (4) calcolare quanto tempo puoi stare al sole prima di scottarti. Tutto resta sul tuo computer.')),
      sezione(NT.t('Immagine personale'), null, boxAvatar, entrata),
      sezione(NT.t('Dati personali'), null,
        campo(NT.t('Sesso'), gruppo('sesso', [['F', NT.t('Donna')], ['M', NT.t('Uomo')], ['altro', NT.t('Altro')], ['', NT.t('Preferisco non dirlo')]], NT.t('Sesso'))),
        campo(NT.t('Data di nascita'), h('div', { class: 'riga-inline' }, nascita, eta))),
      sezione(NT.t('Fenotipo: pelle, capelli, occhi'), NT.t('Se hai dubbi sul fototipo, pensa a come reagisce la tua pelle alla prima esposizione intensa al sole in estate, senza protezione.'),
        campo(NT.t('Fototipo (classificazione di Fitzpatrick)'), fototipi, NT.t('Non lo so: lascia vuoto, puoi tornare più tardi.')),
        campo(NT.t('Colore naturale dei capelli (da giovane)'), gruppo('capelli', [['neri', NT.t('Neri')], ['castani', NT.t('Castani')], ['biondi', NT.t('Biondi')], ['rossi', NT.t('Rossi')], ['grigi', NT.t('Grigi/bianchi')]], NT.t('Capelli'))),
        campo(NT.t('Colore degli occhi'), gruppo('occhi', [['scuri', NT.t('Scuri')], ['verdi', NT.t('Verdi')], ['azzurri', NT.t('Azzurri/grigi')]], NT.t('Occhi'))),
        campo(NT.t('Efelidi (lentiggini)'), gruppo('efelidi', [['nessuna', NT.t('Nessuna')], ['poche', NT.t('Poche')], ['molte', NT.t('Molte')]], NT.t('Efelidi'))),
        campo(NT.t('Quanti nei hai sul corpo, circa?'), gruppo('n_nevi', [['<25', NT.t('Meno di 25')], ['25-49', '25–49'], ['50-99', '50–99'], ['100+', NT.t('100 o più')]], NT.t('Numero di nei')), NT.t('Una stima va bene.')),
        campo(NT.t('Un medico ti ha detto che hai nei atipici (displastici)?'), gruppo('nevi_atipici', [['no', NT.t('No')], ['si', NT.t('Sì')], ['non so', NT.t('Non so')]], NT.t('Nei atipici')))),
      sezione(NT.t('Esposizione al sole'), null,
        campo(NT.t('Scottature con vesciche (soprattutto da bambino o ragazzo)'), gruppo('scottature', [['mai', NT.t('Mai')], ['poche', NT.t('Poche')], ['molte', NT.t('Molte')]], NT.t('Scottature'))),
        campo(NT.t('Lampade o lettini abbronzanti'), gruppo('lampade', [['mai', NT.t('Mai')], ['alcune', NT.t('Qualche volta')], ['spesso', NT.t('Spesso')]], NT.t('Lampade'))),
        spunta('lavoro_aperto', NT.t('Lavoro o faccio attività per molte ore all\'aperto'))),
      sezione(NT.t('Storia personale'), null,
        contatore('melanomi_personali', NT.t('Melanomi già diagnosticati a me'), NT.t('Conta solo i melanomi primari invasivi.')),
        spunta('altri_tumori_cutanei', NT.t('Ho avuto altri tumori della pelle (basalioma, spinalioma)')),
        spunta('immunosoppressione', NT.t('Sono immunosoppresso/a (trapianto o terapie che abbassano le difese)')),
        h('div', { class: 'campo-titolo spazio-su' }, NT.t('Ho avuto (o ho) uno di questi tumori:')),
        h('div', { class: 'spunte-griglia' }, spunta('pers_pancreas', NT.t('Tumore del pancreas')), spunta('pers_astrocitoma', NT.t('Astrocitoma')),
          spunta('pers_uveale', NT.t('Melanoma dell\'occhio (uveale)')), spunta('pers_mesotelioma', NT.t('Mesotelioma')), spunta('pers_rene', NT.t('Carcinoma del rene'))),
        campo(NT.t('Ho già fatto un test genetico per il melanoma?'), gruppo('test_genetico', [['', NT.t('Non indicato')], ['no', NT.t('No')], ['si_positivo', NT.t('Sì, positivo')], ['si_negativo', NT.t('Sì, negativo')], ['si_non_informativo', NT.t('Sì, non informativo')]], NT.t('Test genetico')))),
      sezione(NT.t('Familiarità'), NT.t('Conta i parenti di sangue (non quelli acquisiti) dello stesso lato della famiglia, materno o paterno: è il criterio che usano i genetisti. Se non lo sai, chiedi a un familiare: queste informazioni sono molto utili.'),
        h('label', { class: 'spunta grande' }, h('input', { type: 'checkbox', id: 'ck-fam', checked: !!p.fam_compilata, onchange: ev => cambia('fam_compilata', ev.target.checked) }), ' ' + NT.t('Ho verificato la mia storia familiare (anche se la risposta è «nessuno»)')),
        contatore('fam_melanoma_1grado', NT.t('Parenti di 1° grado con melanoma'), NT.t('Genitori, fratelli, sorelle, figli.')),
        contatore('fam_melanoma_altri', NT.t('Altri parenti con melanoma'), NT.t('Nonni, zii, nipoti (2° grado).')),
        contatore('fam_pancreas', NT.t('Parenti con tumore del pancreas (in tutto)'), NT.t('Di qualsiasi grado di parentela.')),
        contatore('fam_pancreas_1grado', NT.t('…di cui di 1° grado')),
        contatore('fam_astrocitoma', NT.t('Parenti con astrocitoma (tumore del cervello)')),
        contatore('fam_uveale', NT.t('Parenti con melanoma dell\'occhio (uveale)')),
        contatore('fam_mesotelioma', NT.t('Parenti con mesotelioma')),
        contatore('fam_rene', NT.t('Parenti con carcinoma del rene'))),
      sezione(NT.t('Note'), null, h('textarea', { class: 'campo', rows: 3, maxlength: 1000, placeholder: NT.t('Altro che vuoi ricordare (allergie, farmaci fotosensibilizzanti, …)'), value: p.note || '', oninput: ev => cambia('note', ev.target.value) })));

    /* ---------- riepilogo laterale ---------- */
    function disegnaRiepilogo() {
      const ri = S.utente.rischio, ge = S.utente.genetica;
      const colore = { nessuno: 'neutro', alcuni: 'giallo', attenzione: 'arancio' }[ri.livello];
      NT.riempi(riepilogo, 
        h('div', { class: 'scheda' }, h('div', { class: 'riga-spinner' }, NT.avatar(S.utente.nome, 44, S.utente), h('div', {}, h('strong', {}, S.utente.nome),
          h('div', { class: 'piccolo muted' }, [S.utente.eta !== null && S.utente.eta !== undefined ? NT.tp(S.utente.eta, '{n} anno', '{n} anni') : null, S.utente.profilo.fototipo ? NT.t('fototipo {tipo}', { tipo: FOTOTIPI[S.utente.profilo.fototipo - 1][1] }) : null].filter(Boolean).join(' · ') || NT.t('Profilo da completare')))), stato),
        h('div', { class: 'scheda' }, h('h3', {}, NT.t('Fattori di rischio presenti')),
          h('div', { class: 'banda ' + colore }, NT.tr(ri.testo)),
          ri.presenti.length ? h('ul', { class: 'fattori' }, ri.presenti.map(f => h('li', {}, h('span', {}, NT.tr(f.etichetta), f.maggiore ? h('span', { class: 'chip chip-neutro' }, NT.t('rilevante')) : null), f.nota ? h('small', {}, NT.tr(f.nota)) : null))) : null,
          h('p', { class: 'piccolo muted' }, NT.tr(ri.nota))),
        h('div', { class: 'scheda' }, h('h3', {}, NT.t('Melanoma ereditario')),
          h('div', { class: 'banda ' + (ge.esito === 'criteri_soddisfatti' ? 'arancio' : 'neutro') }, NT.tr(ge.messaggio) + (ge.messaggio_aggiunta ? ' ' + NT.tr(ge.messaggio_aggiunta) : '')),
          h('a', { class: 'btn', href: '#/genetica' }, NT.t('Vai alla sezione Genetica'), NT.icona('freccia', 16))));
    }
    disegnaRiepilogo();
    NT.riempi(cont, h('div', { class: 'pagina' }, h('h1', {}, NT.t('Profilo di {nome}', { nome: u.nome })),
      h('div', { class: 'profilo-layout' }, form, riepilogo)));
  };
})();
