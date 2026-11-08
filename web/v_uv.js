/* ============================================================================
   v_uv.js - indice UV di oggi nel luogo scelto (Open-Meteo di default, OpenWeather se scelto)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  /* Categorie dell'OMS (stesse soglie e colori del programma Python) */
  const CAT = [[11, 'Estremo', '#8e44ad'], [8, 'Molto alto', '#d9261c'], [6, 'Alto', '#f28c00'], [3, 'Moderato', '#e8c400'], [0, 'Basso', '#3f9c35']];
  const cat = v => CAT.find(c => v >= c[0]) || CAT[CAT.length - 1];
  const FOTOTIPI = ['I', 'II', 'III', 'IV', 'V', 'VI'];

  function grafico(ore) {
    const W = 720, H = 230, sx = 44, dx = 12, su = 18, giu = 40;
    const larg = (W - sx - dx) / ore.length;
    const massimo = Math.max(11, Math.ceil(Math.max(...ore.map(o => o.uvi))) + 1);
    const y = v => su + (H - su - giu) * (1 - v / massimo);
    let s = '<svg class="grafico-uv" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Indice UV ora per ora nelle prossime 24 ore">';
    for (let t = 0; t <= massimo; t += (massimo > 12 ? 4 : 2)) {
      s += '<line class="gl" x1="' + sx + '" x2="' + (W - dx) + '" y1="' + y(t) + '" y2="' + y(t) + '"/><text class="gt" x="' + (sx - 8) + '" y="' + (y(t) + 4) + '" text-anchor="end">' + t + '</text>';
    }
    ore.forEach((o, i) => {
      const x = sx + i * larg + larg * 0.14, w = larg * 0.72, c = cat(o.uvi);
      const alt = Math.max(o.uvi > 0 ? 2 : 0, y(0) - y(o.uvi));
      s += '<rect x="' + x.toFixed(1) + '" y="' + (y(0) - alt).toFixed(1) + '" width="' + w.toFixed(1) + '" height="' + alt.toFixed(1) + '" rx="2" fill="' + c[2] + '"><title>' +
        NT.esc(o.giorno + ' ore ' + o.ora + ': indice UV ' + NT.num(o.uvi) + ' (' + c[1] + ')') + '</title></rect>';
      const cambio = i === 0 || o.giorno !== ore[i - 1].giorno;
      const vicinoCambio = [-2, -1, 1, 2].some(k => ore[i + k] && ore[i + k - 1] && ore[i + k].giorno !== ore[i + k - 1].giorno);
      if (cambio || (i % 3 === 0 && !vicinoCambio)) {
        s += '<text class="gt" x="' + (x + w / 2).toFixed(1) + '" y="' + (H - giu + 16) + '" text-anchor="middle">' + NT.esc(o.ora.slice(0, 2)) + '</text>';
        if (i === 0 || o.giorno !== ore[i - 1].giorno) s += '<text class="gt g6t" x="' + (x + w / 2).toFixed(1) + '" y="' + (H - giu + 32) + '" text-anchor="middle">' + NT.esc(o.giorno) + '</text>';
      }
    });
    s += '<line class="gline" x1="' + sx + '" x2="' + (W - dx) + '" y1="' + y(3) + '" y2="' + y(3) + '" stroke-dasharray="5 4"/>' +
      '<text class="gt g6t" x="' + (W - dx) + '" y="' + (y(3) - 5) + '" text-anchor="end">3 = da qui l\'OMS consiglia protezione</text></svg>';
    return NT.html(s);
  }

  NT.viste.uv = async function (cont) {
    S.imp = await NT.get('/api/impostazioni');
    let attivo = true;
    NT.alCambioPagina(() => { attivo = false; });
    const barra = h('section', { class: 'scheda' });
    const risultato = h('div', { class: 'uv-risultato' });

    /* ---------------- scelta del luogo ---------------- */
    async function salvaPos(lat, lon, nome) {
      try {
        S.imp = await NT.api('PUT', '/api/impostazioni', { lat, lon, localita: nome });
        NT.toast('Posizione salvata: ' + nome, 'ok');
        disegnaBarra(); carica();
      } catch (e) { NT.errore(e); }
    }
    function rileva() {
      if (!navigator.geolocation) { NT.toast('Questo browser non offre la geolocalizzazione: cerca la città per nome.', 'errore'); return; }
      NT.toast('Chiedo la posizione al browser… (potrebbe comparire una richiesta di permesso)', 'info');
      navigator.geolocation.getCurrentPosition(
        p => salvaPos(p.coords.latitude, p.coords.longitude, 'La mia posizione (' + NT.num(p.coords.latitude, 2) + '; ' + NT.num(p.coords.longitude, 2) + ')'),
        err => NT.toast(err.code === 1 ? 'Permesso negato. Puoi cercare la città per nome oppure usare la stima da indirizzo internet.' : 'Il computer non riesce a determinare la posizione. Cerca la città per nome.', 'errore'),
        { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 });
    }
    async function daIP() {
      const ok = await NT.conferma('Stima dall\'indirizzo internet', 'Per stimare la città il programma contatta il servizio gratuito ipwho.is, che vede il tuo indirizzo internet. La precisione è quella della città (a volte sbaglia). Procedo?', { si: 'Sì, stima la città' });
      if (!ok) return;
      try { const r = await NT.get('/api/posizione-ip'); await salvaPos(r.lat, r.lon, r.nome || 'Posizione stimata'); }
      catch (e) { NT.errore(e); }
    }
    const campoCitta = h('input', { type: 'search', class: 'campo', placeholder: 'Cerca una città (es. Torino)', maxlength: 80, 'aria-label': 'Nome della città' });
    const elencoCitta = h('div', { class: 'citta-elenco' });
    async function cercaCitta() {
      const q = campoCitta.value.trim();
      if (q.length < 2) return;
      NT.riempi(elencoCitta, NT.caricamento('Cerco…'));
      try {
        const r = await NT.get('/api/localita?q=' + encodeURIComponent(q));
        NT.riempi(elencoCitta, r.length ? r.map(c => h('button', { class: 'btn citta-voce', onclick: () => salvaPos(c.lat, c.lon, c.nome) }, NT.icona('posizione', 16), c.nome))
          : h('div', { class: 'piccolo muted' }, 'Nessuna città trovata con questo nome.'));
      } catch (e) { NT.riempi(elencoCitta, h('div', { class: 'errore-campo' }, e.message)); }
    }
    campoCitta.addEventListener('keydown', e => { if (e.key === 'Enter') cercaCitta(); });

    function disegnaBarra() {
      const ho = S.imp.lat !== null && S.imp.lat !== undefined;
      NT.riempi(barra, 
        h('div', { class: 'uv-posizione' }, NT.icona('posizione', 22),
          h('div', {}, h('strong', {}, ho ? (S.imp.localita || 'Posizione impostata') : 'Posizione non impostata'),
            h('div', { class: 'piccolo muted' }, ho ? NT.num(S.imp.lat, 3) + '; ' + NT.num(S.imp.lon, 3) : 'Scegli dove ti trovi per vedere l\'indice UV di oggi.'))),
        h('div', { class: 'riga-inline spazio-su' }, h('button', { class: 'btn btn-pri', onclick: rileva }, NT.icona('mirino', 18), 'Rileva la mia posizione'),
          campoCitta, h('button', { class: 'btn', onclick: cercaCitta }, 'Cerca')),
        elencoCitta,
        h('div', { class: 'piccolo muted spazio-su' }, 'La posizione resta salvata solo su questo computer; viene inviata al servizio meteo (coordinate arrotondate) per ottenere l\'indice UV. ',
          h('button', { class: 'btn-testo', onclick: daIP }, 'Non riesci? Stima dall\'indirizzo internet')));
    }

    /* ---------------- indice UV ---------------- */
    async function carica() {
      if (S.imp.lat === null || S.imp.lat === undefined) {
        NT.riempi(risultato, NT.vuoto('Manca la posizione', 'Scegli la città qui sopra: poi vedrai l\'indice UV di oggi, ora per ora.'));
        return;
      }
      NT.riempi(risultato, NT.caricamento('Scarico l\'indice UV…'));
      const ft = S.utente && S.utente.profilo.fototipo ? S.utente.profilo.fototipo : 0;
      let d;
      try { d = await NT.get('/api/uv?fototipo=' + ft + '&localita=' + encodeURIComponent(S.imp.localita || '')); }
      catch (e) { if (attivo) NT.riempi(risultato, h('div', { class: 'scheda errore-pagina' }, h('h2', {}, 'Indice UV non disponibile'), h('p', {}, e.message), h('button', { class: 'btn', onclick: carica }, 'Riprova'))); return; }
      if (!attivo) return;
      const cm = d.categoria_max, co = d.categoria_ora;
      const sc = d.scottatura_max;
      NT.riempi(risultato, 
        d.avviso ? h('div', { class: 'banda giallo' }, d.avviso, ' ', h('a', { href: '#/impostazioni' }, 'Impostazioni')) : null,
        h('section', { class: 'scheda uv-verdetto uv-' + d.verdetto.livello },
          h('div', { class: 'uv-titolo' }, h('h2', {}, d.verdetto.titolo), h('p', {}, d.verdetto.testo)),
          h('div', { class: 'uv-numeri' },
            h('div', { class: 'uv-num' }, h('span', { class: 'uv-val', style: { background: co.colore, color: co.colore === '#e8c400' ? '#222' : '#fff' } }, NT.num(d.uvi_ora)), h('div', {}, h('strong', {}, 'Adesso'), h('div', { class: 'piccolo' }, co.nome))),
            h('div', { class: 'uv-num' }, h('span', { class: 'uv-val', style: { background: cm.colore, color: cm.colore === '#e8c400' ? '#222' : '#fff' } }, NT.num(d.uvi_max)), h('div', {}, h('strong', {}, 'Massimo di oggi'), h('div', { class: 'piccolo' }, cm.nome))))),
        h('section', { class: 'scheda' }, h('h2', {}, 'Prossime ' + d.ore.length + ' ore'), d.ore.length ? grafico(d.ore) : NT.vuoto('Dati orari non disponibili'),
          h('div', { class: 'piccolo muted' }, 'Fonte: ' + d.fonte + ' · aggiornato ' + d.aggiornato + (d.fuso ? ' · ' + d.fuso : ''),
            d.fonte === 'Open-Meteo' ? [' · ', NT.link('https://open-meteo.com/', 'Open-Meteo.com'), ' (CC BY 4.0)'] : null)),
        h('section', { class: 'scheda' }, h('h2', {}, 'Cosa fare'), h('p', {}, cm.consiglio),
          sc ? h('div', { class: 'banda neutro' }, h('strong', {}, 'Con il tuo fototipo (' + FOTOTIPI[S.utente.profilo.fototipo - 1] + ')'), ': a cielo sereno e senza protezione, al picco di oggi la pelle può arrossarsi in ',
            h('strong', {}, sc.testo), '. È una stima prudente che usa la dose minima di eritema più bassa del tuo fototipo; con riflessi (acqua, neve, sabbia), quota o pelle già arrossata il tempo si accorcia.')
            : h('div', { class: 'piccolo muted' }, S.utente ? ['Per vedere quanto sole ti scotta, indica il fototipo nel ', h('a', { href: '#/profilo' }, 'Profilo'), '.'] : 'Scegli un utente e indica il suo fototipo per vedere quanti minuti servono per scottarsi.'),
          h('ul', { class: 'punti' },
            h('li', {}, 'Le ore centrali (circa 11-16) sono quelle con l\'indice più alto.'),
            h('li', {}, 'Le nuvole sottili non fermano gran parte degli UV: l\'indice può restare alto anche con il cielo velato.'),
            h('li', {}, 'Chi ha tanti nei, nei atipici o una storia di melanoma dovrebbe proteggersi anche con indici moderati.'),
            h('li', {}, 'L\'indice è una previsione: il valore reale dipende da nuvole, quota e riflessi.'))),
        h('section', { class: 'scheda' }, h('h2', {}, 'Come si legge l\'indice UV'),
          h('div', { class: 'legenda-uv' }, CAT.slice().reverse().map(c => h('span', { class: 'chip', style: { background: c[2], color: c[0] === 3 ? '#222' : '#fff' } }, c[1] + ' (' + (c[0] === 11 ? '11+' : c[0] + '–' + ({ 0: 2, 3: 5, 6: 7, 8: 10 }[c[0]])) + ')'))),
          h('p', { class: 'piccolo muted' }, 'Soglie e colori della scala internazionale dell\'OMS. Fonti:'),
          h('ul', { class: 'fonti' }, d.fonti.map(f => h('li', {}, NT.link(f.url, f.titolo))))));
    }

    disegnaBarra();
    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, 'Indice UV di oggi'),
      h('p', { class: 'lead' }, 'I raggi ultravioletti sono il principale fattore di rischio modificabile per il melanoma. Qui vedi quanto sono forti oggi dove ti trovi.'),
      barra, risultato));
    carica();
  };
})();
