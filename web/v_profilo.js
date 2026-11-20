/* ============================================================================
   v_profilo.js - phenotype, personal history and family history (saves by itself)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  const FOTOTIPI = [
    [1, 'I', NT.t('Very fair skin. Always burns, never tans (often red hair, freckles).')],
    [2, 'II', NT.t('Fair skin. Burns easily, tans little.')],
    [3, 'III', NT.t('Fair-olive skin. Sometimes burns, tans gradually.')],
    [4, 'IV', NT.t('Olive skin. Burns little, tans easily.')],
    [5, 'V', NT.t('Dark skin. Rarely burns.')],
    [6, 'VI', NT.t('Very dark skin. Does not burn.')],
  ];

  NT.viste.profilo = async function (cont) {
    const u = S.utente;
    let p = Object.assign({}, u.profilo);
    let daSalvare = false;                // true between an edit and the automatic save
    const stato = h('span', { class: 'salvataggio' }, '');
    const riepilogo = h('aside', { class: 'riepilogo-profilo' });

    /* ---------- automatic saving ---------- */
    const salvaOra = async () => {
      daSalvare = false;
      stato.textContent = NT.t('Saving…'); stato.className = 'salvataggio';
      try {
        const r = await NT.api('PUT', '/api/utenti/' + u.id + '/profilo', p);
        S.utente = Object.assign(S.utente, r);
        stato.textContent = NT.t('Saved ✓'); stato.className = 'salvataggio ok';
        disegnaRiepilogo();
      } catch (e) { stato.textContent = ''; NT.errore(e); }
    };
    const salva = NT.debounce(salvaOra, 700);
    const cambia = (campo, valore) => { p[campo] = valore; daSalvare = true; stato.textContent = NT.t('Unsaved changes…'); stato.className = 'salvataggio'; salva(); };
    NT.alCambioPagina(() => { if (daSalvare) salvaOra(); });

    /* ---------- small components ---------- */
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
        h('div', { class: 'contatore' }, h('button', { type: 'button', class: 'btn-icona', 'aria-label': NT.t('Decrease: {voce}', { voce: testo }), onclick: () => agg(-1) }, NT.icona('meno', 16)), val,
          h('button', { type: 'button', class: 'btn-icona', 'aria-label': NT.t('Increase: {voce}', { voce: testo }), onclick: () => agg(1) }, NT.icona('piu', 16))));
    };

    /* ---------- phototype ---------- */
    const COL = window.Corpo.colorePelle;
    const fototipi = h('div', { class: 'fototipi', role: 'radiogroup', 'aria-label': NT.t('Phototype') }, FOTOTIPI.map(([n, r, d]) => h('button', { type: 'button', role: 'radio', class: 'fototipo' + (p.fototipo === n ? ' sel' : ''),
      'aria-checked': p.fototipo === n ? 'true' : 'false', dataset: { n: String(n) },
      onclick: () => { p.fototipo = p.fototipo === n ? 0 : n; NT.$$('.fototipo', fototipi).forEach(b => { const on = +b.dataset.n === p.fototipo; b.classList.toggle('sel', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); }); cambia('fototipo', p.fototipo); } },
      h('span', { class: 'swatch', style: { background: COL(n) } }), h('span', {}, h('strong', {}, NT.t('Type {n}', { n: r })), h('small', {}, d)))));

    const eta = h('span', { class: 'eta-calcolata' }, '');
    const aggiornaEta = () => {
      if (!p.data_nascita) { eta.textContent = ''; return; }
      const n = new Date(p.data_nascita + 'T12:00:00'), o = new Date();
      let a = o.getFullYear() - n.getFullYear(); if (o < new Date(o.getFullYear(), n.getMonth(), n.getDate())) a--;
      eta.textContent = a >= 0 ? NT.tp(a, '{n} year', '{n} years') : '';
    };
    const nascita = h('input', { type: 'date', class: 'campo corto', value: p.data_nascita || '', min: '1900-01-01', max: NT.oggiISO(),
      onchange: ev => { cambia('data_nascita', ev.target.value); aggiornaEta(); } });
    aggiornaEta();

    const sezione = (titolo, intro, ...figli) => h('section', { class: 'scheda' }, h('h2', {}, titolo), intro ? h('p', { class: 'piccolo muted' }, intro) : null, ...figli);

    /* ---------- personal image ---------- */
    const boxAvatar = h('div', { class: 'avatar-editor' });
    const entrata = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/bmp', hidden: true, 'aria-label': NT.t('Choose a personal picture') });
    const aggiornaAvatar = v => { S.utente.avatar_v = v; disegnaAvatar(); NT.ridisegnaTestata(); disegnaRiepilogo(); };
    async function scegliAvatar() {
      const file = entrata.files && entrata.files[0];
      entrata.value = '';
      if (!file) return;
      try {
        if (file.size > 40 * 1024 * 1024) throw new Error(NT.t('The file is too large (maximum 40 MB).'));
        const blob = await NT.ridimensionaQuadrato(file, 256);      // square crop at the centre + reduction, in the browser
        const r = await NT.api('POST', '/api/utenti/' + u.id + '/avatar', null, { raw: blob, tipo: 'image/jpeg' });
        aggiornaAvatar(r.avatar_v);
        NT.toast(NT.t('Personal picture saved.'), 'ok');
      } catch (e) { NT.errore(e); }
    }
    async function togliAvatar() {
      try { const r = await NT.api('DELETE', '/api/utenti/' + u.id + '/avatar'); aggiornaAvatar(r.avatar_v); NT.toast(NT.t('Picture removed.'), 'ok'); }
      catch (e) { NT.errore(e); }
    }
    entrata.addEventListener('change', scegliAvatar);
    function disegnaAvatar() {
      NT.riempi(boxAvatar, NT.avatar(u.nome, 88, S.utente),
        h('div', { class: 'avatar-azioni' },
          h('p', { class: 'piccolo muted' }, NT.t('You can use your own photo, a drawing or an icon. The image is cropped to a square and reduced, stays only on this computer and is never used for mole analysis.')),
          h('div', { class: 'riga-inline' },
            h('button', { type: 'button', class: 'btn', onclick: () => entrata.click() }, S.utente.avatar_v ? NT.t('Change image…') : NT.t('Choose image…')),
            S.utente.avatar_v ? h('button', { type: 'button', class: 'btn-testo pericolo', onclick: togliAvatar }, NT.t('Remove')) : null)));
    }
    disegnaAvatar();

    const form = h('div', { class: 'pila' },
      h('div', { class: 'scheda info' }, h('strong', {}, NT.t('What is this information used for?') + ' '),
        NT.t('They do not change the result of the neural networks, which only look at the pixels of the photo. They are used to: (1) put the risk in context, (2) choose the scientific literature suited to you, (3) check the criteria for genetic counselling, (4) calculate how long you can stay in the sun before burning. Everything stays on your computer.')),
      sezione(NT.t('Personal picture'), null, boxAvatar, entrata),
      sezione(NT.t('Personal data'), null,
        campo(NT.t('Sex'), gruppo('sesso', [['F', NT.t('Woman')], ['M', NT.t('Man')], ['altro', NT.t('Other')], ['', NT.t('I prefer not to say')]], NT.t('Sex'))),
        campo(NT.t('Date of birth'), h('div', { class: 'riga-inline' }, nascita, eta))),
      sezione(NT.t('Phenotype: skin, hair, eyes'), NT.t('If you are unsure about your phototype, think about how your skin reacts to the first intense sun exposure in summer, without protection.'),
        campo(NT.t('Phototype (Fitzpatrick classification)'), fototipi, NT.t("I don't know: leave it empty, you can come back later.")),
        campo(NT.t('Natural hair colour (when young)'), gruppo('capelli', [['neri', NT.t('Black')], ['castani', NT.t('Brown')], ['biondi', NT.t('Blond')], ['rossi', NT.t('Red')], ['grigi', NT.t('Grey/white')]], NT.t('Hair'))),
        campo(NT.t('Eye colour'), gruppo('occhi', [['scuri', NT.t('Dark')], ['verdi', NT.t('Green')], ['azzurri', NT.t('Blue/grey')]], NT.t('Eyes'))),
        campo(NT.t('Freckles (ephelides)'), gruppo('efelidi', [['nessuna', NT.t('None')], ['poche', NT.t('A few')], ['molte', NT.t('Many')]], NT.t('Freckles'))),
        campo(NT.t('Roughly how many moles do you have on your body?'), gruppo('n_nevi', [['<25', NT.t('Fewer than 25')], ['25-49', '25–49'], ['50-99', '50–99'], ['100+', NT.t('100 or more')]], NT.t('Number of moles')), NT.t('An estimate is fine.')),
        campo(NT.t('Has a doctor told you that you have atypical (dysplastic) moles?'), gruppo('nevi_atipici', [['no', NT.t('No')], ['si', NT.t('Yes')], ['non so', NT.t("Don't know")]], NT.t('Atypical moles')))),
      sezione(NT.t('Sun exposure'), null,
        campo(NT.t('Sunburns with blisters (especially as a child or teenager)'), gruppo('scottature', [['mai', NT.t('Never')], ['poche', NT.t('A few')], ['molte', NT.t('Many')]], NT.t('Sunburns'))),
        campo(NT.t('Tanning lamps or sunbeds'), gruppo('lampade', [['mai', NT.t('Never')], ['alcune', NT.t('Sometimes')], ['spesso', NT.t('Often')]], NT.t('Sunbeds'))),
        spunta('lavoro_aperto', NT.t('I work or do activities outdoors for many hours'))),
      sezione(NT.t('Personal history'), null,
        contatore('melanomi_personali', NT.t('Melanomas already diagnosed in me'), NT.t('Only invasive primary melanomas count.')),
        spunta('altri_tumori_cutanei', NT.t('I have had other skin cancers (basal cell or squamous cell carcinoma)')),
        spunta('immunosoppressione', NT.t("I am immunosuppressed (transplant or therapies that lower the body's defences)")),
        h('div', { class: 'campo-titolo spazio-su' }, NT.t('I have had (or have) one of these cancers:')),
        h('div', { class: 'spunte-griglia' }, spunta('pers_pancreas', NT.t('Pancreatic cancer')), spunta('pers_astrocitoma', NT.t('Astrocytoma')),
          spunta('pers_uveale', NT.t('Melanoma of the eye (uveal)')), spunta('pers_mesotelioma', NT.t('Mesothelioma')), spunta('pers_rene', NT.t('Kidney carcinoma'))),
        campo(NT.t('Have I already had a genetic test for melanoma?'), gruppo('test_genetico', [['', NT.t('Not specified')], ['no', NT.t('No')], ['si_positivo', NT.t('Yes, positive')], ['si_negativo', NT.t('Yes, negative')], ['si_non_informativo', NT.t('Yes, uninformative')]], NT.t('Genetic test')))),
      sezione(NT.t('Family history'), NT.t('Count blood relatives (not in-laws) on the same side of the family, maternal or paternal: this is the criterion geneticists use. If you do not know, ask a relative: this information is very useful.'),
        h('label', { class: 'spunta grande' }, h('input', { type: 'checkbox', id: 'ck-fam', checked: !!p.fam_compilata, onchange: ev => cambia('fam_compilata', ev.target.checked) }), ' ' + NT.t('I have checked my family history (even if the answer is «none»)')),
        contatore('fam_melanoma_1grado', NT.t('1st-degree relatives with melanoma'), NT.t('Parents, brothers, sisters, children.')),
        contatore('fam_melanoma_altri', NT.t('Other relatives with melanoma'), NT.t('Grandparents, aunts and uncles, nieces and nephews (2nd degree).')),
        contatore('fam_pancreas', NT.t('Relatives with pancreatic cancer (in total)'), NT.t('Of any degree of kinship.')),
        contatore('fam_pancreas_1grado', NT.t('…of which 1st-degree')),
        contatore('fam_astrocitoma', NT.t('Relatives with astrocytoma (brain tumour)')),
        contatore('fam_uveale', NT.t('Relatives with melanoma of the eye (uveal)')),
        contatore('fam_mesotelioma', NT.t('Relatives with mesothelioma')),
        contatore('fam_rene', NT.t('Relatives with kidney carcinoma'))),
      sezione(NT.t('Notes'), null, h('textarea', { class: 'campo', rows: 3, maxlength: 1000, placeholder: NT.t('Anything else you want to remember (allergies, photosensitising medicines, …)'), value: p.note || '', oninput: ev => cambia('note', ev.target.value) })));

    /* ---------- side summary ---------- */
    function disegnaRiepilogo() {
      const ri = S.utente.rischio, ge = S.utente.genetica;
      const colore = { nessuno: 'neutro', alcuni: 'giallo', attenzione: 'arancio' }[ri.livello];
      NT.riempi(riepilogo, 
        h('div', { class: 'scheda' }, h('div', { class: 'riga-spinner' }, NT.avatar(S.utente.nome, 44, S.utente), h('div', {}, h('strong', {}, S.utente.nome),
          h('div', { class: 'piccolo muted' }, [S.utente.eta !== null && S.utente.eta !== undefined ? NT.tp(S.utente.eta, '{n} year', '{n} years') : null, S.utente.profilo.fototipo ? NT.t('phototype {tipo}', { tipo: FOTOTIPI[S.utente.profilo.fototipo - 1][1] }) : null].filter(Boolean).join(' · ') || NT.t('Profile to complete')))), stato),
        h('div', { class: 'scheda' }, h('h3', {}, NT.t('Risk factors present')),
          h('div', { class: 'banda ' + colore }, NT.tr(ri.testo)),
          ri.presenti.length ? h('ul', { class: 'fattori' }, ri.presenti.map(f => h('li', {}, h('span', {}, NT.tr(f.etichetta), f.maggiore ? h('span', { class: 'chip chip-neutro' }, NT.t('significant')) : null), f.nota ? h('small', {}, NT.tr(f.nota)) : null))) : null,
          h('p', { class: 'piccolo muted' }, NT.tr(ri.nota))),
        h('div', { class: 'scheda' }, h('h3', {}, NT.t('Hereditary melanoma')),
          h('div', { class: 'banda ' + (ge.esito === 'criteri_soddisfatti' ? 'arancio' : 'neutro') }, NT.tr(ge.messaggio) + (ge.messaggio_aggiunta ? ' ' + NT.tr(ge.messaggio_aggiunta) : '')),
          h('a', { class: 'btn', href: '#/genetica' }, NT.t('Go to the Genetics section'), NT.icona('freccia', 16))));
    }
    disegnaRiepilogo();
    NT.riempi(cont, h('div', { class: 'pagina' }, h('h1', {}, NT.t('Profile of {nome}', { nome: u.nome })),
      h('div', { class: 'profilo-layout' }, form, riepilogo)));
  };
})();
