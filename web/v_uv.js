/* ============================================================================
   v_uv.js - today's UV index in the chosen place (Open-Meteo by default, OpenWeather if chosen)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  /* WHO categories (same thresholds and colours as the Python program) */
  const CAT = [[11, NT.m('Extreme'), '#8e44ad'], [8, NT.m('Very high'), '#d9261c'], [6, NT.m('High'), '#f28c00'], [3, NT.m('Moderate'), '#e8c400'], [0, NT.m('Low'), '#3f9c35']];
  const cat = v => CAT.find(c => v >= c[0]) || CAT[CAT.length - 1];
  const FOTOTIPI = ['I', 'II', 'III', 'IV', 'V', 'VI'];

  function grafico(ore) {
    const W = 720, H = 230, sx = 44, dx = 12, su = 18, giu = 40;
    const larg = (W - sx - dx) / ore.length;
    const giorno = o => o.data ? NT.fmtGiornoMese(o.data) : o.giorno;       // 'data' = YYYY-MM-DD
    const massimo = Math.max(11, Math.ceil(Math.max(...ore.map(o => o.uvi))) + 1);
    const y = v => su + (H - su - giu) * (1 - v / massimo);
    let s = '<svg class="grafico-uv" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + NT.esc(NT.t('Hour-by-hour UV index for the next 24 hours')) + '">';
    for (let t = 0; t <= massimo; t += (massimo > 12 ? 4 : 2)) {
      s += '<line class="gl" x1="' + sx + '" x2="' + (W - dx) + '" y1="' + y(t) + '" y2="' + y(t) + '"/><text class="gt" x="' + (sx - 8) + '" y="' + (y(t) + 4) + '" text-anchor="end">' + t + '</text>';
    }
    ore.forEach((o, i) => {
      const x = sx + i * larg + larg * 0.14, w = larg * 0.72, c = cat(o.uvi);
      const alt = Math.max(o.uvi > 0 ? 2 : 0, y(0) - y(o.uvi));
      s += '<rect x="' + x.toFixed(1) + '" y="' + (y(0) - alt).toFixed(1) + '" width="' + w.toFixed(1) + '" height="' + alt.toFixed(1) + '" rx="2" fill="' + c[2] + '"><title>' +
        NT.esc(NT.t('{giorno} at {ora}: UV index {uvi} ({categoria})', { giorno: giorno(o), ora: o.ora, uvi: NT.num(o.uvi), categoria: NT.t(c[1]) })) + '</title></rect>';
      const cambio = i === 0 || o.giorno !== ore[i - 1].giorno;
      const vicinoCambio = [-2, -1, 1, 2].some(k => ore[i + k] && ore[i + k - 1] && ore[i + k].giorno !== ore[i + k - 1].giorno);
      if (cambio || (i % 3 === 0 && !vicinoCambio)) {
        s += '<text class="gt" x="' + (x + w / 2).toFixed(1) + '" y="' + (H - giu + 16) + '" text-anchor="middle">' + NT.esc(o.ora.slice(0, 2)) + '</text>';
        if (i === 0 || o.giorno !== ore[i - 1].giorno) s += '<text class="gt g6t" x="' + (x + w / 2).toFixed(1) + '" y="' + (H - giu + 32) + '" text-anchor="middle">' + NT.esc(giorno(o)) + '</text>';
      }
    });
    s += '<line class="gline" x1="' + sx + '" x2="' + (W - dx) + '" y1="' + y(3) + '" y2="' + y(3) + '" stroke-dasharray="5 4"/>' +
      '<text class="gt g6t" x="' + (W - dx) + '" y="' + (y(3) - 5) + '" text-anchor="end">' + NT.esc(NT.t('3 = WHO recommends protection from this level')) + '</text></svg>';
    return NT.html(s);
  }

  NT.viste.uv = async function (cont) {
    S.imp = await NT.get('/api/impostazioni');
    let attivo = true;
    NT.alCambioPagina(() => { attivo = false; });
    const barra = h('section', { class: 'scheda' });
    const risultato = h('div', { class: 'uv-risultato' });

    /* ---------------- choosing the place ---------------- */
    async function salvaPos(lat, lon, nome) {
      try {
        S.imp = await NT.api('PUT', '/api/impostazioni', { lat, lon, localita: nome });
        NT.toast(NT.t('Location saved: {nome}', { nome: nome }), 'ok');
        disegnaBarra(); carica();
      } catch (e) { NT.errore(e); }
    }
    function rileva() {
      if (!navigator.geolocation) { NT.toast(NT.t('This browser does not offer geolocation: search for the city by name.'), 'errore'); return; }
      NT.toast(NT.t('Asking the browser for your position… (a permission request may appear)'), 'info');
      navigator.geolocation.getCurrentPosition(
        p => salvaPos(p.coords.latitude, p.coords.longitude, NT.t('My location ({lat}; {lon})', { lat: NT.num(p.coords.latitude, 2), lon: NT.num(p.coords.longitude, 2) })),
        err => NT.toast(err.code === 1 ? NT.t('Permission denied. You can search for the city by name or use the estimate from the internet address.') : NT.t('The computer cannot determine the position. Search for the city by name.'), 'errore'),
        { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 });
    }
    async function daIP() {
      const ok = await NT.conferma(NT.t('Estimate from the internet address'), NT.t('To estimate the city, the program contacts the free service ipwho.is, which sees your internet address. Accuracy is at city level (it is sometimes wrong). Proceed?'), { si: NT.t('Yes, estimate the city') });
      if (!ok) return;
      try { const r = await NT.get('/api/posizione-ip'); await salvaPos(r.lat, r.lon, r.nome || NT.t('Estimated location')); }
      catch (e) { NT.errore(e); }
    }
    const campoCitta = h('input', { type: 'search', class: 'campo', placeholder: NT.t('Search for a city (e.g. Turin)'), maxlength: 80, 'aria-label': NT.t('City name') });
    const elencoCitta = h('div', { class: 'citta-elenco' });
    async function cercaCitta() {
      const q = campoCitta.value.trim();
      if (q.length < 2) return;
      NT.riempi(elencoCitta, NT.caricamento(NT.t('Searching…')));
      try {
        const r = await NT.get('/api/localita?q=' + encodeURIComponent(q));
        NT.riempi(elencoCitta, r.length ? r.map(c => h('button', { class: 'btn citta-voce', onclick: () => salvaPos(c.lat, c.lon, c.nome) }, NT.icona('posizione', 16), c.nome))
          : h('div', { class: 'piccolo muted' }, NT.t('No city found with this name.')));
      } catch (e) { NT.riempi(elencoCitta, h('div', { class: 'errore-campo' }, e.message)); }
    }
    campoCitta.addEventListener('keydown', e => { if (e.key === 'Enter') cercaCitta(); });

    function disegnaBarra() {
      const ho = S.imp.lat !== null && S.imp.lat !== undefined;
      NT.riempi(barra, 
        h('div', { class: 'uv-posizione' }, NT.icona('posizione', 22),
          h('div', {}, h('strong', {}, ho ? (S.imp.localita || NT.t('Location set')) : NT.t('Location not set')),
            h('div', { class: 'piccolo muted' }, ho ? NT.num(S.imp.lat, 3) + '; ' + NT.num(S.imp.lon, 3) : NT.t("Choose where you are to see today's UV index.")))),
        h('div', { class: 'riga-inline spazio-su' }, h('button', { class: 'btn btn-pri', onclick: rileva }, NT.icona('mirino', 18), NT.t('Detect my location')),
          campoCitta, h('button', { class: 'btn', onclick: cercaCitta }, NT.t('Search'))),
        elencoCitta,
        h('div', { class: 'piccolo muted spazio-su' }, NT.t('The location is saved only on this computer; it is sent to the weather service (rounded coordinates) to get the UV index.') + ' ',
          h('button', { class: 'btn-testo', onclick: daIP }, NT.t("Can't do it? Estimate from the internet address"))));
    }

    /* ---------------- UV index ---------------- */
    async function carica() {
      if (S.imp.lat === null || S.imp.lat === undefined) {
        NT.riempi(risultato, NT.vuoto(NT.t('Location missing'), NT.t("Choose the city above: then you will see today's UV index, hour by hour.")));
        return;
      }
      NT.riempi(risultato, NT.caricamento(NT.t('Downloading the UV index…')));
      const ft = S.utente && S.utente.profilo.fototipo ? S.utente.profilo.fototipo : 0;
      let d;
      try { d = await NT.get('/api/uv?fototipo=' + ft + '&localita=' + encodeURIComponent(S.imp.localita || '')); }
      catch (e) { if (attivo) NT.riempi(risultato, h('div', { class: 'scheda errore-pagina' }, h('h2', {}, NT.t('UV index not available')), h('p', {}, e.message), h('button', { class: 'btn', onclick: carica }, NT.t('Try again')))); return; }
      if (!attivo) return;
      const cm = d.categoria_max, co = d.categoria_ora;
      const sc = d.scottatura_max;
      NT.riempi(risultato, 
        d.avviso ? h('div', { class: 'banda giallo' }, NT.tr(d.avviso), ' ', h('a', { href: '#/impostazioni' }, NT.t('Settings'))) : null,
        h('section', { class: 'scheda uv-verdetto uv-' + d.verdetto.livello },
          h('div', { class: 'uv-titolo' }, h('h2', {}, NT.tr(d.verdetto.titolo)), h('p', {}, NT.tr(d.verdetto.testo))),
          h('div', { class: 'uv-numeri' },
            h('div', { class: 'uv-num' }, h('span', { class: 'uv-val', style: { background: co.colore, color: co.colore === '#e8c400' ? '#222' : '#fff' } }, NT.num(d.uvi_ora)), h('div', {}, h('strong', {}, NT.t('Now')), h('div', { class: 'piccolo' }, NT.tr(co.nome)))),
            h('div', { class: 'uv-num' }, h('span', { class: 'uv-val', style: { background: cm.colore, color: cm.colore === '#e8c400' ? '#222' : '#fff' } }, NT.num(d.uvi_max)), h('div', {}, h('strong', {}, NT.t("Today's maximum")), h('div', { class: 'piccolo' }, NT.tr(cm.nome)))))),
        h('section', { class: 'scheda' }, h('h2', {}, NT.t('Next {n} hours', { n: d.ore.length })), d.ore.length ? grafico(d.ore) : NT.vuoto(NT.t('Hourly data not available')),
          h('div', { class: 'piccolo muted' }, NT.t('Source:') + ' ' + d.fonte + ' · ' + NT.t('updated') + ' ' + (d.aggiornato_iso ? NT.fmtDataOra(d.aggiornato_iso) + ' ' + NT.t('(local time at the location)') : d.aggiornato) + (d.fuso ? ' · ' + d.fuso : ''),
            d.fonte === 'Open-Meteo' ? [' · ', NT.link('https://open-meteo.com/', 'Open-Meteo.com'), ' (CC BY 4.0)'] : null)),
        h('section', { class: 'scheda' }, h('h2', {}, NT.t('What to do')), h('p', {}, NT.tr(cm.consiglio)),
          sc ? h('div', { class: 'banda neutro' }, h('strong', {}, NT.t('With your phototype ({fototipo})', { fototipo: FOTOTIPI[S.utente.profilo.fototipo - 1] })), ': ' + NT.t("in clear skies and without protection, at today's peak the skin may redden in") + ' ',
            h('strong', {}, NT.tr(sc.testo)), '. ' + NT.t('This is a cautious estimate that uses the lowest minimal erythema dose for your phototype; with reflections (water, snow, sand), altitude or already reddened skin the time is shorter.'))
            : h('div', { class: 'piccolo muted' }, S.utente ? [NT.t('To see how much sun burns you, enter your phototype in the') + ' ', h('a', { href: '#/profilo' }, NT.t('Profile')), '.'] : NT.t('Choose a user and enter their phototype to see how many minutes it takes to burn.')),
          h('ul', { class: 'punti' },
            h('li', {}, NT.t('The middle hours of the day (about 11–16) have the highest index.')),
            h('li', {}, NT.t('Thin clouds do not stop much of the UV: the index can stay high even with a hazy sky.')),
            h('li', {}, NT.t('People with many moles, atypical moles or a history of melanoma should protect themselves even when the index is moderate.')),
            h('li', {}, NT.t('The index is a forecast: the actual value depends on clouds, altitude and reflections.')))),
        h('section', { class: 'scheda' }, h('h2', {}, NT.t('How to read the UV index')),
          h('div', { class: 'legenda-uv' }, CAT.slice().reverse().map(c => h('span', { class: 'chip', style: { background: c[2], color: c[0] === 3 ? '#222' : '#fff' } }, NT.t(c[1]) + ' (' + (c[0] === 11 ? '11+' : c[0] + '–' + ({ 0: 2, 3: 5, 6: 7, 8: 10 }[c[0]])) + ')'))),
          h('p', { class: 'piccolo muted' }, NT.t('Thresholds and colours of the WHO international scale. Sources:')),
          h('ul', { class: 'fonti' }, d.fonti.map(f => h('li', {}, NT.link(f.url, NT.tr(f.titolo)))))));
    }

    disegnaBarra();
    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, NT.t("Today's UV index")),
      h('p', { class: 'lead' }, NT.t('Ultraviolet rays are the main modifiable risk factor for melanoma. Here you can see how strong they are today where you are.')),
      barra, risultato));
    carica();
  };
})();
