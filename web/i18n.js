/* ============================================================================
   i18n.js - lingue dell'interfaccia (italiano, inglese, francese, tedesco, spagnolo)

   Come funziona, in breve:
   - Il TESTO ITALIANO è l'originale e fa da chiave: nel codice si scrive NT.t('Salva neo').
   - I dizionari delle altre lingue (i18n_en.js, i18n_fr.js, ...) associano a ogni testo italiano la
     sua traduzione. Se la lingua è l'italiano non serve nessun dizionario.
   - I testi con valori variabili usano segnaposto con nome: NT.t('{n} giorni fa', { n: 3 }).
   - I testi che arrivano dal programma Python (messaggi di errore, criteri di genetica, indice UV...)
     sono ancora in italiano: NT.tr() li traduce cercandoli nel dizionario (anche per "forma",
     cioè con i valori variabili al posto dei segnaposto).
   - La lingua si sceglie nelle Impostazioni ("auto" = come il browser). Il server la scrive nella pagina
     (<meta name="nt-lingua">) così è nota prima di disegnare qualsiasi cosa.
   Per aggiungere una lingua vedi CONTRIBUTING.md.
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT = window.NT || {};

  NT.LINGUE = [['it', 'Italiano'], ['en', 'English'], ['fr', 'Français'], ['de', 'Deutsch'], ['es', 'Español']];
  const CODICI = NT.LINGUE.map(l => l[0]);

  /* ---------- quale lingua usare ---------- */
  NT.linguaDelBrowser = function () {
    const elenco = (navigator.languages && navigator.languages.length) ? navigator.languages : [navigator.language || ''];
    for (const l of elenco) {
      const c = String(l).slice(0, 2).toLowerCase();
      if (CODICI.includes(c)) return c;
    }
    return 'en';                                  // lingua non supportata: l'inglese è la più diffusa
  };
  const meta = document.querySelector('meta[name="nt-lingua"]');
  NT.linguaScelta = meta && CODICI.includes(meta.content) ? meta.content : 'auto';    // 'auto' oppure un codice
  NT.lingua = NT.linguaScelta === 'auto' ? NT.linguaDelBrowser() : NT.linguaScelta;
  document.documentElement.lang = NT.lingua;

  const DIZ = (window.NT_DIZIONARI || {})[NT.lingua] || {};   // vuoto per l'italiano

  /* ---------- traduzione dei testi del programma ---------- */
  const sostituisci = (s, params) => params ? s.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m)) : s;

  NT.mancanti = new Set();       // testi senza traduzione trovati durante l'uso (li controllano i test)
  NT.t = function (testo, params) {
    let s = testo;
    if (NT.lingua !== 'it') {
      const tr = DIZ[testo];
      if (tr === undefined) {
        if (!NT.mancanti.has(testo)) { NT.mancanti.add(testo); console.warn('[i18n] manca la traduzione (' + NT.lingua + '): ' + testo); }
      } else s = tr;
    }
    return sostituisci(s, params);
  };

  /* Segna un testo italiano che verrà tradotto più tardi (con NT.tr): non fa nulla, serve a build.py per
     controllare che il testo abbia la traduzione in tutti i dizionari. */
  NT.m = testo => testo;

  /* Singolare/plurale: 'uno' e 'altri' sono i due testi italiani (con {n}). Il francese usa il singolare anche per 0.
     Se in italiano le due forme sono uguali (es. "{n} foto") la traduzione del plurale ha la chiave "{n} foto#pl". */
  NT.tp = function (n, uno, altri, params) {
    const sing = NT.lingua === 'fr' ? Math.abs(n) < 2 : n === 1;
    const p = Object.assign({ n: n }, params);
    if (NT.lingua === 'it') return sostituisci(sing ? uno : altri, p);
    return NT.t(sing ? uno : (altri === uno ? uno + '#pl' : altri), p);
  };

  /* Traduce un testo che viene dal programma Python (già composto, in italiano). Non protesta se non lo trova:
     può essere un nome scritto dall'utente o il testo di un errore tecnico. */
  let schemi = null;
  function costruisciSchemi() {
    schemi = [];
    for (const chiave in DIZ) {
      if (!/\{\w+\}/.test(chiave)) continue;
      const pezzi = chiave.split(/\{(\w+)\}/);          // [testo, nome, testo, nome, ..., testo]
      const nomi = [];
      let re = '^';
      pezzi.forEach((p, i) => {
        if (i % 2) { nomi.push(p); re += '([\\s\\S]+?)'; }
        else re += p.replace(/[.*+?^$()|[\]\\{}]/g, '\\$&');
      });
      schemi.push({ chiave: chiave, nomi: nomi, re: new RegExp(re + '$'), fisso: pezzi.filter((p, i) => i % 2 === 0).join('').length });
    }
    schemi.sort((a, b) => b.fisso - a.fisso);              // prima le forme più specifiche
  }
  NT.tr = function tr(testo) {
    if (testo === null || testo === undefined || testo === '' || NT.lingua === 'it') return testo;
    testo = String(testo);
    if (Object.prototype.hasOwnProperty.call(DIZ, testo)) return DIZ[testo];
    if (!schemi) costruisciSchemi();
    for (const s of schemi) {
      const m = s.re.exec(testo);
      if (!m) continue;
      const params = {};
      s.nomi.forEach((nome, i) => { params[nome] = tr(m[i + 1]); });
      return sostituisci(DIZ[s.chiave], params);
    }
    if (testo.indexOf('; ') > 0) {                           // più messaggi uniti da "; "
      const parti = testo.split('; '), tradotte = parti.map(tr);
      if (tradotte.some((x, i) => x !== parti[i])) return tradotte.join('; ');
    }
    return testo;
  };

  /* ---------- numeri e date nel formato della lingua ---------- */
  const SEP = NT.lingua === 'en' ? '.' : ',';
  const MESI_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const LOCALI = { it: 'it-IT', en: 'en-GB', fr: 'fr-FR', de: 'de-DE', es: 'es-ES' };
  NT.locale = LOCALI[NT.lingua];
  NT.num = (n, dec) => (n === null || n === undefined) ? '' : Number(n).toFixed(dec === undefined ? 1 : dec).replace('.', SEP);
  NT.perc = v => v === null || v === undefined ? '' : (v * 100).toFixed(v >= 0.995 || v < 0.01 ? 1 : 0).replace('.', SEP) + '%';
  NT.migliaia = n => Number(n).toLocaleString(NT.locale);
  /* 'AAAA-MM-GG' -> 08/11/2026 (it, fr, es), 08.11.2026 (de), 8 Nov 2026 (en) */
  NT.fmtData = iso => {
    if (!iso) return '';
    const [a, m, g] = iso.slice(0, 10).split('-');
    if (NT.lingua === 'en') return String(+g) + ' ' + MESI_EN[+m - 1] + ' ' + a;
    return g + (NT.lingua === 'de' ? '.' + m + '.' : '/' + m + '/') + a;
  };
  NT.fmtDataOra = iso => iso ? NT.fmtData(iso) + ' ' + String(iso).slice(11, 16) : '';
  /* giorno e mese senza anno: 08/11, 08.11., 8 Nov */
  NT.fmtGiornoMese = iso => {
    if (!iso) return '';
    const [, m, g] = iso.slice(0, 10).split('-');
    if (NT.lingua === 'en') return String(+g) + ' ' + MESI_EN[+m - 1];
    return g + (NT.lingua === 'de' ? '.' + m + '.' : '/' + m);
  };
  NT.fraseGiorni = g => g === null || g === undefined ? '' : g <= 0 ? NT.t('oggi') : g === 1 ? NT.t('ieri')
    : g < 60 ? NT.t('{n} giorni fa', { n: g })
      : g < 700 ? NT.t('{n} mesi fa', { n: Math.round(g / 30.4) })
        : NT.tp(Math.round(g / 365), '{n} anno fa', '{n} anni fa');
})();
