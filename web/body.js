/* ============================================================================
   body.js - mappa interattiva del corpo umano (fronte + retro) disegnata in SVG
   Le coordinate di ogni neo sono salvate "normalizzate": x e y da 0 a 1 dentro la
   figura (fronte o retro). Cosi' restano valide qualunque sia lo zoom o la finestra.
   ============================================================================ */
(function () {
  'use strict';
  const LARG = 400, ALT = 900;            // dimensioni di UNA figura
  const VB_W = 800, VB_H = 930;           // area completa: fronte (0-400) + retro (400-800)
  const CX = 200;
  const NS = 'http://www.w3.org/2000/svg';

  const f = n => Math.round(n * 100) / 100;

  /* ---------- geometria: curve morbide e "tubi" per gli arti ---------- */
  function curva(pts, chiusa) {
    const n = pts.length;
    const get = i => chiusa ? pts[(i + n) % n] : pts[Math.max(0, Math.min(n - 1, i))];
    let d = 'M' + f(pts[0][0]) + ' ' + f(pts[0][1]);
    const fine = chiusa ? n : n - 1;
    for (let i = 0; i < fine; i++) {
      const p0 = get(i - 1), p1 = get(i), p2 = get(i + 1), p3 = get(i + 2);
      d += 'C' + f(p1[0] + (p2[0] - p0[0]) / 6) + ' ' + f(p1[1] + (p2[1] - p0[1]) / 6) + ' ' +
        f(p2[0] - (p3[0] - p1[0]) / 6) + ' ' + f(p2[1] - (p3[1] - p1[1]) / 6) + ' ' + f(p2[0]) + ' ' + f(p2[1]);
    }
    return chiusa ? d + 'Z' : d;
  }

  const PER = 8;                           // punti calcolati tra due punti guida
  function campiona(punti) {
    const out = [], n = punti.length;
    const get = i => punti[Math.max(0, Math.min(n - 1, i))];
    for (let i = 0; i < n - 1; i++) {
      const p0 = get(i - 1), p1 = get(i), p2 = get(i + 1), p3 = get(i + 2);
      for (let k = 0; k < PER; k++) {
        const t = k / PER, t2 = t * t, t3 = t2 * t;
        const c = j => 0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2 +
          (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3);
        out.push([c(0), c(1), c(2)]);
      }
    }
    out.push(punti[n - 1].slice());
    return out;
  }

  /* bordi sinistro e destro di un tubo (punti guida [x, y, raggio]) */
  function bordi(punti, extra) {
    const d = campiona(punti), L = [], R = [];
    for (let i = 0; i < d.length; i++) {
      const a = d[Math.max(0, i - 1)], b = d[Math.min(d.length - 1, i + 1)];
      let tx = b[0] - a[0], ty = b[1] - a[1];
      const l = Math.hypot(tx, ty) || 1; tx /= l; ty /= l;
      const r = d[i][2] + (extra || 0);
      L.push([d[i][0] - ty * r, d[i][1] + tx * r]);
      R.push([d[i][0] + ty * r, d[i][1] - tx * r]);
    }
    return { L, R };
  }
  const aPath = poly => 'M' + poly.map(p => f(p[0]) + ' ' + f(p[1])).join('L') + 'Z';
  function tuboPoly(punti, extra) { const b = bordi(punti, extra); return b.L.concat(b.R.slice().reverse()); }
  /* tratto di tubo tra due punti guida (indici), leggermente allargato: serve per le regioni */
  function trattoPoly(punti, i0, i1, extra) {
    const b = bordi(punti, extra || 0);
    const a = i0 * PER, z = i1 * PER;
    return b.L.slice(a, z + 1).concat(b.R.slice(a, z + 1).reverse());
  }
  const specchia = punti => punti.map(p => [LARG - p[0]].concat(p.slice(1)));
  const rect = (x0, y0, x1, y1) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
  const specchiaPoly = poly => poly.map(p => [LARG - p[0], p[1]]);

  /* ---------- anatomia (lato sinistro dello schermo; il destro e' lo specchio) ---------- */
  const BRACCIO = [[124, 190, 22], [116, 225, 19], [108, 262, 17], [101, 300, 14.5], [95, 332, 15],
    [89, 372, 12.5], [83, 405, 9.5], [79, 430, 13.5], [76, 458, 12.5], [73, 484, 7]];
  const GAMBA = [[168, 478, 34], [166, 540, 31], [164, 590, 26], [162, 622, 22.5], [161, 652, 21],
    [160, 680, 20], [160, 720, 18], [159, 765, 15.5], [158, 800, 11.5], [158, 825, 10]];
  const COLLO = [[200, 116, 17], [200, 140, 17.5], [200, 154, 19]];
  const TORSO_SX = [[20, 136], [40, 148], [64, 160], [82, 172], [84, 188], [70, 214], [64, 236], [62, 268],
    [57, 305], [49, 340], [46, 372], [50, 408], [58, 440], [64, 470], [58, 494]];
  const TESTA = [[200, 34], [228, 44], [236, 74], [232, 100], [218, 124], [200, 132], [182, 124], [168, 100],
    [164, 74], [172, 44]];
  const PIEDE_F = [[158, 822, 10], [156, 842, 12.5], [152, 860, 14]];
  const PIEDE_R = [[158, 822, 10], [158, 846, 12.5], [158, 858, 11]];

  function sagoma(vista) {
    const torso = TORSO_SX.map(p => [CX - p[0], p[1]])
      .concat([[CX, 510]], TORSO_SX.slice().reverse().map(p => [CX + p[0], p[1]]));
    const forme = [curva(torso, true), curva(TESTA, true), aPath(tuboPoly(COLLO)),
      aPath(tuboPoly(BRACCIO)), aPath(tuboPoly(specchia(BRACCIO))),
      aPath(tuboPoly(GAMBA)), aPath(tuboPoly(specchia(GAMBA)))];
    const piede = vista === 'fronte' ? PIEDE_F : PIEDE_R;
    forme.push(aPath(tuboPoly(piede)), aPath(tuboPoly(specchia(piede))));
    // orecchie
    forme.push(ellisse(164, 86, 5.5, 11), ellisse(236, 86, 5.5, 11));
    // spalle (deltoidi), punte delle mani e dei piedi arrotondate
    for (const [x, y, r] of [BRACCIO[0], BRACCIO[9], piede[2]]) forme.push(cerchio(x, y, r), cerchio(LARG - x, y, r));
    return forme;
  }
  function ellisse(cx, cy, rx, ry) {
    return 'M' + f(cx - rx) + ' ' + f(cy) + 'a' + rx + ' ' + ry + ' 0 1 0 ' + (2 * rx) + ' 0a' + rx + ' ' + ry + ' 0 1 0 ' + (-2 * rx) + ' 0Z';
  }
  const cerchio = (cx, cy, r) => ellisse(cx, cy, r, r);

  /* ---------- regioni cliccabili ---------- */
  // genere: 'm' maschile (destro/sinistro), 'f' femminile (destra/sinistra), '' nessun lato
  function regioni(vista) {
    const R = [];
    const lato = (schermoSx) => (vista === 'fronte') === schermoSx ? 'destr' : 'sinistr';
    // aggiunge una regione sul lato sinistro dello schermo e il suo specchio sul destro
    function coppia(nome, genere, poly) {
      const suff = genere === 'f' ? 'a' : 'o';
      R.push({ nome: nome + ' ' + lato(true) + suff, poly: poly });
      R.push({ nome: nome + ' ' + lato(false) + suff, poly: specchiaPoly(poly) });
    }
    const singola = (nome, poly) => R.push({ nome: nome, poly: poly });
    const fr = vista === 'fronte';

    // testa e collo (ordine: dal piu' grande al piu' piccolo, cosi' le piccole stanno sopra)
    if (fr) {
      singola('Fronte e cuoio capelluto', rect(150, 24, 250, 58));
      singola('Viso', rect(150, 58, 250, 136));
    } else {
      singola('Cuoio capelluto (testa)', rect(150, 24, 250, 122));
    }
    if (fr) singola('Collo', rect(168, 128, 232, 170));
    else singola('Nuca e collo', rect(168, 116, 232, 170));
    // tronco
    if (fr) {
      coppia('Torace', 'm', rect(134, 160, 200, 302));
      coppia('Addome alto', 'm', rect(138, 302, 200, 378));
      coppia('Addome basso', 'm', rect(134, 378, 200, 444));
      coppia('Inguine', 'm', rect(130, 444, 200, 512));
    } else {
      coppia('Regione scapolare', 'f', rect(134, 160, 200, 264));
      coppia('Schiena (zona media)', 'f', rect(138, 264, 200, 346));
      coppia('Regione lombare', 'f', rect(134, 346, 200, 442));
      coppia('Gluteo', 'm', rect(130, 442, 200, 524));
    }
    // arti: tratti dello stesso tubo del disegno, un po' piu' larghi, poi ritagliati sulla sagoma
    const e = 7;
    coppia('Spalla', 'f', trattoPoly(BRACCIO, 0, 1, e));
    coppia('Braccio', 'm', trattoPoly(BRACCIO, 1, 3, e));
    coppia('Gomito', 'm', trattoPoly(BRACCIO, 3, 4, e));
    coppia('Avambraccio', 'm', trattoPoly(BRACCIO, 4, 6, e));
    coppia('Mano', 'f', trattoPoly(BRACCIO, 6, 9, e + 3));
    coppia('Coscia', 'f', trattoPoly(GAMBA, 0, 3, e));
    if (fr) {
      coppia('Ginocchio', 'm', trattoPoly(GAMBA, 3, 5, e));
      coppia('Gamba (stinco)', 'f', trattoPoly(GAMBA, 5, 8, e));
    } else {
      coppia('Cavo popliteo', 'm', trattoPoly(GAMBA, 3, 5, e));
      coppia('Polpaccio', 'm', trattoPoly(GAMBA, 5, 8, e));
    }
    coppia('Caviglia', 'f', trattoPoly(GAMBA, 8, 9, e));
    coppia('Piede', 'm', rect(128, 822, 200, 880));
    // orecchie (sopra la testa)
    coppia('Orecchio', 'm', rect(150, 70, 168, 104));
    return R;
  }

  /* ---------- colori ---------- */
  const PELLE = { 0: '#ead9c8', 1: '#f6e0d2', 2: '#efcab0', 3: '#e0b390', 4: '#c58f68', 5: '#9b6a48', 6: '#6a4630' };
  const colorePelle = ft => PELLE[ft] || PELLE[0];

  /* ---------- dettagli anatomici (linee leggere) ---------- */
  function dettagli(vista) {
    const L = [];
    const l = (d, extra) => L.push('<path d="' + d + '" fill="none" ' + (extra || '') + '/>');
    const sp = (d) => d; // segnaposto
    if (vista === 'fronte') {
      l('M192 160Q165 154 140 168'); l('M208 160Q235 154 260 168');
      l('M142 232Q172 256 198 240'); l('M258 232Q228 256 202 240');
      L.push('<circle cx="167" cy="254" r="2.6" class="det-pieno"/>', '<circle cx="233" cy="254" r="2.6" class="det-pieno"/>');
      l('M200 262L200 376');
      L.push('<ellipse cx="200" cy="386" rx="3.2" ry="4.6" class="det-pieno"/>');
      l('M148 454Q176 470 200 494'); l('M252 454Q224 470 200 494');
      L.push('<ellipse cx="161" cy="652" rx="9" ry="11" fill="none"/>', '<ellipse cx="239" cy="652" rx="9" ry="11" fill="none"/>');
    } else {
      l('M200 138L199 220L201 330L200 470');
      l('M176 188Q150 196 152 232Q160 262 180 258'); l('M224 188Q250 196 248 232Q240 262 220 258');
      l('M200 446L200 510');
      l('M138 468Q164 524 200 512'); l('M262 468Q236 524 200 512');
      l('M150 656Q162 662 174 656'); l('M250 656Q238 662 226 656');
    }
    return L.join('');
  }

  /* ---------- costruzione dell'SVG di una figura ---------- */
  function figura(vista, ft, ox) {
    const id = vista === 'fronte' ? 'f' : 'r';
    const forme = sagoma(vista);
    const reg = regioni(vista);
    const colore = colorePelle(ft);
    let s = '<g transform="translate(' + ox + ',20)" data-vista="' + vista + '">';
    s += '<clipPath id="sil-' + id + '">' + forme.map(d => '<path d="' + d + '"/>').join('') + '</clipPath>';
    s += '<g class="contorno">' + forme.map(d => '<path d="' + d + '"/>').join('') + '</g>';
    s += '<g class="pelle" fill="' + colore + '">' + forme.map(d => '<path d="' + d + '"/>').join('') + '</g>';
    s += '<g class="dettagli" clip-path="url(#sil-' + id + ')">' + dettagli(vista) + '</g>';
    s += '<g class="regioni" clip-path="url(#sil-' + id + ')">' +
      reg.map(r => '<polygon points="' + r.poly.map(p => f(p[0]) + ',' + f(p[1])).join(' ') + '" data-regione="' + r.nome + '"/>').join('') + '</g>';
    s += '</g>';
    return s;
  }

  function svgCompleto(ft) {
    let s = '<svg xmlns="' + NS + '" class="corpo-svg" viewBox="0 0 ' + VB_W + ' ' + VB_H + '" preserveAspectRatio="xMidYMid meet" role="img" ' +
      'aria-label="' + esc(window.NT.t('Mappa del corpo umano: fronte a sinistra, retro a destra')) + '">';
    s += figura('fronte', ft, 0) + figura('retro', ft, LARG);
    // etichette fisse
    const D = esc(window.NT.t('D')), Sx = esc(window.NT.t('S'));          // destra / sinistra del paziente
    s += '<g class="etichette">' +
      '<text x="200" y="14" text-anchor="middle">' + esc(window.NT.t('FRONTE')) + '</text><text x="600" y="14" text-anchor="middle">' + esc(window.NT.t('RETRO')) + '</text>' +
      '<text x="22" y="64" class="lato">' + D + '</text><text x="378" y="64" text-anchor="end" class="lato">' + Sx + '</text>' +
      '<text x="422" y="64" class="lato">' + Sx + '</text><text x="778" y="64" text-anchor="end" class="lato">' + D + '</text></g>';
    s += '<g class="marcatori"></g></svg>';
    return s;
  }

  /* ============================================================================
     Classe MappaCorpo: zoom, trascinamento, aggiunta e spostamento dei nei
     ============================================================================ */
  class MappaCorpo {
    constructor(contenitore, cb) {
      this.box = contenitore;
      this.cb = cb || {};
      this.ft = 0;
      this.nei = [];
      this.selId = null;
      this.aggiunta = false;
      this.bozza = null;
      this.vb = { x: 0, y: 0, w: VB_W, h: VB_H };
      this.zoom = 1;
      this.drag = null;
      this.ricostruisci();
      this.ro = new ResizeObserver(() => this.disegnaMarcatori());
      this.ro.observe(this.box);
    }

    ricostruisci() {
      this.box.innerHTML = svgCompleto(this.ft);
      this.svg = this.box.querySelector('svg');
      this.gMarc = this.svg.querySelector('.marcatori');
      this.applicaVB();
      this.collega();
      this.disegnaMarcatori();
    }

    setFototipo(ft) { if (ft !== this.ft) { this.ft = ft; this.ricostruisci(); } }

    setNei(nei, selId) { this.nei = nei; this.selId = selId; this.disegnaMarcatori(); }
    setSelezione(id) { this.selId = id; this.disegnaMarcatori(); }
    modalitaAggiunta(on) {
      this.aggiunta = on;
      this.svg.classList.toggle('aggiunta', on);
      if (!on) this.bozza = null;
      this.disegnaMarcatori();
    }
    setBozza(b) { this.bozza = b; this.disegnaMarcatori(); }

    /* ---- vista (zoom e spostamento) ---- */
    applicaVB() {
      const v = this.vb;
      this.svg.setAttribute('viewBox', f(v.x) + ' ' + f(v.y) + ' ' + f(v.w) + ' ' + f(v.h));
    }
    limita() {
      const v = this.vb;
      v.w = VB_W / this.zoom; v.h = VB_H / this.zoom;
      v.x = Math.max(0, Math.min(VB_W - v.w, v.x));
      v.y = Math.max(0, Math.min(VB_H - v.h, v.y));
    }
    zoomSu(fattore, cx, cy) {
      const nuovo = Math.max(1, Math.min(12, this.zoom * fattore));
      if (nuovo === this.zoom) return;
      if (cx == null) { cx = this.vb.x + this.vb.w / 2; cy = this.vb.y + this.vb.h / 2; }
      const rx = (cx - this.vb.x) / this.vb.w, ry = (cy - this.vb.y) / this.vb.h;   // punto fisso sotto il cursore
      this.zoom = nuovo;
      this.vb.w = VB_W / nuovo; this.vb.h = VB_H / nuovo;
      this.vb.x = cx - rx * this.vb.w; this.vb.y = cy - ry * this.vb.h;
      this.limita(); this.applicaVB(); this.disegnaMarcatori();
    }
    reset() { this.zoom = 1; this.vb = { x: 0, y: 0, w: VB_W, h: VB_H }; this.applicaVB(); this.disegnaMarcatori(); }
    centraSu(nevo, zoom) {
      const p = this.posizione(nevo.vista, nevo.x, nevo.y);
      this.zoom = zoom || Math.max(this.zoom, 4);
      this.vb.w = VB_W / this.zoom; this.vb.h = VB_H / this.zoom;
      this.vb.x = p.x - this.vb.w / 2; this.vb.y = p.y - this.vb.h / 2;
      this.limita(); this.applicaVB(); this.disegnaMarcatori();
    }

    /* ---- conversioni tra coordinate dello schermo e della figura ---- */
    posizione(vista, x, y) {         // da normalizzate (0-1) a coordinate dell'SVG
      return { x: (vista === 'retro' ? LARG : 0) + x * LARG, y: 20 + y * ALT };
    }
    daSchermo(ev) {                  // da pixel a { vista, x, y } normalizzati
      const pt = this.svg.createSVGPoint();
      pt.x = ev.clientX; pt.y = ev.clientY;
      const p = pt.matrixTransform(this.svg.getScreenCTM().inverse());
      const vista = p.x >= LARG ? 'retro' : 'fronte';
      const x = (p.x - (vista === 'retro' ? LARG : 0)) / LARG, y = (p.y - 20) / ALT;
      return { vista, x, y, px: p.x, py: p.y };
    }
    regioneA(ev) {                   // nome della regione sotto il puntatore (o '')
      const els = document.elementsFromPoint(ev.clientX, ev.clientY);
      for (const el of els) if (el.dataset && el.dataset.regione) return el.dataset.regione;
      return '';
    }
    dentroCorpo(ev) {
      return document.elementsFromPoint(ev.clientX, ev.clientY).some(el => el.dataset && el.dataset.regione);
    }
    scala() { const m = this.svg.getScreenCTM(); return m ? 1 / m.a : 1; }

    /* ---- marcatori ---- */
    disegnaMarcatori() {
      if (!this.gMarc) return;
      const k = this.scala();
      let s = '';
      const mostraNome = this.zoom >= 3;
      for (const n of this.nei) {
        if (n.archiviato) continue;
        const p = this.posizione(n.vista, n.x, n.y);
        const sel = n.id === this.selId;
        const cls = 'marc' + (sel ? ' sel' : '') + (n.flag ? ' flag' : '') + (n.senzaFoto ? ' vuoto' : '');
        s += '<g class="' + cls + '" data-id="' + n.id + '" transform="translate(' + f(p.x) + ',' + f(p.y) + ') scale(' + f(k) + ')">' +
          (sel ? '<circle class="alone" r="17"/>' : '') +
          '<circle class="area" r="15"/><circle class="punto" r="9"/>' +
          '<text class="num" y="3.4" text-anchor="middle">' + n.num + '</text>' +
          (mostraNome ? '<text class="nome" x="14" y="4">' + esc(n.nome) + '</text>' : '') + '</g>';
      }
      if (this.bozza) {
        const p = this.posizione(this.bozza.vista, this.bozza.x, this.bozza.y);
        s += '<g class="marc bozza" transform="translate(' + f(p.x) + ',' + f(p.y) + ') scale(' + f(k) + ')">' +
          '<circle class="area" r="16"/><circle class="punto" r="9"/><path d="M-15 0H-5M5 0H15M0 -15V-5M0 5V15" class="mirino"/></g>';
      }
      s += '<g class="fantasma" style="display:none" transform="scale(' + f(k) + ')"><circle r="8"/><path d="M-12 0H-4M4 0H12M0 -12V-4M0 4V12"/></g>';
      this.gMarc.innerHTML = s;
      this.fantasma = this.gMarc.querySelector('.fantasma');
    }

    /* ---- interazione ---- */
    collega() {
      const svg = this.svg;
      svg.addEventListener('wheel', ev => {
        ev.preventDefault();
        const p = this.daSchermo(ev);
        this.zoomSu(ev.deltaY < 0 ? 1.18 : 1 / 1.18, p.px, p.py);
      }, { passive: false });

      svg.addEventListener('pointerdown', ev => {
        if (ev.button !== 0) return;
        const marc = ev.target.closest && ev.target.closest('.marc:not(.fantasma)');
        const dati = { sx: ev.clientX, sy: ev.clientY, mosso: false, vb0: Object.assign({}, this.vb), id: ev.pointerId };
        if (marc) {
          dati.tipo = marc.classList.contains('bozza') ? 'bozza' : 'marc';
          dati.nid = marc.dataset.id ? parseInt(marc.dataset.id, 10) : null;
        } else dati.tipo = 'sfondo';
        this.drag = dati;
        svg.setPointerCapture(ev.pointerId);
      });

      svg.addEventListener('pointermove', ev => {
        const d = this.drag;
        if (d && d.id === ev.pointerId) {
          const dx = ev.clientX - d.sx, dy = ev.clientY - d.sy;
          if (!d.mosso && Math.hypot(dx, dy) > 5) d.mosso = true;
          if (d.mosso) {
            if (d.tipo === 'sfondo' && !this.aggiunta) {                       // trascinamento della vista
              const k = this.scala();
              this.vb.x = d.vb0.x - dx * k; this.vb.y = d.vb0.y - dy * k;
              this.limita(); this.applicaVB();
              svg.classList.add('trascina');
            } else if (d.tipo === 'marc' || d.tipo === 'bozza') {              // spostamento di un neo
              if (d.tipo === 'marc' && d.nid !== this.selId) return;           // si sposta solo il neo selezionato
              const p = this.daSchermo(ev);
              if (this.dentroCorpo(ev)) {
                d.pos = { vista: p.vista, x: Math.max(0, Math.min(1, p.x)), y: Math.max(0, Math.min(1, p.y)) };
                if (d.tipo === 'bozza') this.bozza = Object.assign({}, this.bozza, d.pos);
                else { const n = this.nei.find(q => q.id === d.nid); if (n) Object.assign(n, d.pos); }
                this.disegnaMarcatori();
              }
            }
          }
        }
        // etichetta della regione e puntatore "fantasma"
        if (this.cb.onRegione && !(d && d.mosso)) this.cb.onRegione(this.regioneA(ev));
        if (this.aggiunta && this.fantasma && !(d && d.mosso)) {
          const p = this.daSchermo(ev);
          if (this.dentroCorpo(ev)) {
            this.fantasma.style.display = '';
            this.fantasma.setAttribute('transform', 'translate(' + f(p.px) + ',' + f(p.py) + ') scale(' + f(this.scala()) + ')');
          } else this.fantasma.style.display = 'none';
        }
      });

      const fine = ev => {
        const d = this.drag;
        if (!d || d.id !== ev.pointerId) return;
        this.drag = null;
        svg.classList.remove('trascina');
        try { svg.releasePointerCapture(ev.pointerId); } catch (e) { /* gia' rilasciato */ }
        if (ev.type === 'pointercancel') { this.disegnaMarcatori(); return; }
        if (d.mosso && d.pos) {                                                // fine dello spostamento
          const reg = this.regioneA(ev);
          if (d.tipo === 'bozza') this.cb.onBozzaMossa && this.cb.onBozzaMossa(Object.assign({ regione: reg }, d.pos));
          else this.cb.onSposta && this.cb.onSposta(d.nid, Object.assign({ regione: reg }, d.pos));
          return;
        }
        if (d.mosso) return;                                                   // era un trascinamento della vista
        // semplice clic
        if (d.tipo === 'marc') { this.cb.onSeleziona && this.cb.onSeleziona(d.nid); return; }
        if (d.tipo === 'bozza') return;
        if (this.aggiunta) {
          if (!this.dentroCorpo(ev)) return;
          const p = this.daSchermo(ev);
          this.cb.onPunto && this.cb.onPunto({ vista: p.vista, x: p.x, y: p.y, regione: this.regioneA(ev) });
        } else this.cb.onSeleziona && this.cb.onSeleziona(null);
      };
      svg.addEventListener('pointerup', fine);
      svg.addEventListener('pointercancel', fine);
      svg.addEventListener('pointerleave', () => {
        if (this.fantasma) this.fantasma.style.display = 'none';
        this.cb.onRegione && this.cb.onRegione('');
      });
      svg.addEventListener('dblclick', ev => {
        if (this.aggiunta) return;
        const p = this.daSchermo(ev); this.zoomSu(2, p.px, p.py);
      });
    }
  }

  function esc(t) {
    return String(t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  window.Corpo = { MappaCorpo, colorePelle, regioni, svgCompleto, LARG, ALT };
})();
