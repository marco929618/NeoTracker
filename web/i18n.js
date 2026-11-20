/* ============================================================================
   i18n.js - interface languages (English, Italian, French, German, Spanish)

   How it works, in short:
   - The ENGLISH text is the source and also the key: the code writes NT.t('Save mole').
   - The dictionaries i18n_it.js, i18n_fr.js, i18n_de.js and i18n_es.js map every English text to its
     translation. English itself needs no dictionary.
   - Texts with variable values use named placeholders: NT.t('{n} days ago', { n: 3 }).
   - Texts that come from the Python program (error messages, genetics criteria, UV index...) are English
     too: NT.tr() translates them by looking them up in the dictionary (also by "shape", i.e. with the
     variable values in place of the placeholders).
   - Data saved by earlier versions contains the Italian text of that time: NT.tr() recognises it by
     looking it up among the Italian translations, so old records are shown in the current language.
   - The language is chosen in Settings ("auto" = same as the browser). The server writes it into the
     page (<meta name="nt-lingua">) so that it is known before anything is drawn.
   To add a language see CONTRIBUTING.md.
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT = window.NT || {};

  NT.LINGUE = [['en', 'English'], ['it', 'Italiano'], ['fr', 'Français'], ['de', 'Deutsch'], ['es', 'Español']];
  const CODICI = NT.LINGUE.map(l => l[0]);

  /* ---------- which language to use ---------- */
  NT.linguaDelBrowser = function () {
    const elenco = (navigator.languages && navigator.languages.length) ? navigator.languages : [navigator.language || ''];
    for (const l of elenco) {
      const c = String(l).slice(0, 2).toLowerCase();
      if (CODICI.includes(c)) return c;
    }
    return 'en';                                  // unsupported language: English is the most widespread
  };
  const meta = document.querySelector('meta[name="nt-lingua"]');
  NT.linguaScelta = meta && CODICI.includes(meta.content) ? meta.content : 'auto';    // 'auto' or a language code
  NT.lingua = NT.linguaScelta === 'auto' ? NT.linguaDelBrowser() : NT.linguaScelta;
  document.documentElement.lang = NT.lingua;

  const DIZIONARI = window.NT_DIZIONARI || {};
  const DIZ = NT.lingua === 'en' ? {} : (DIZIONARI[NT.lingua] || {});   // empty for English (the source)
  const IT = DIZIONARI.it || {};              // every English text is a key here: it is the list of all texts

  /* ---------- translation of the program's texts ---------- */
  const sostituisci = (s, params) => params ? s.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m)) : s;

  NT.mancanti = new Set();       // texts without a translation found during use (the tests check this set)
  NT.t = function (testo, params) {
    let s = testo;
    if (NT.lingua !== 'en') {
      const tr = DIZ[testo];
      if (tr === undefined) {
        if (!NT.mancanti.has(testo)) { NT.mancanti.add(testo); console.warn('[i18n] missing translation (' + NT.lingua + '): ' + testo); }
      } else s = tr;
    }
    return sostituisci(s, params);
  };

  /* Marks an English text that will be translated later (with NT.tr): it does nothing, but build.py uses it
     to check that the text has a translation in every dictionary. */
  NT.m = testo => testo;

  /* Singular/plural: 'uno' and 'altri' are the two English texts (with {n}). French uses the singular for 0 too.
     If the two English forms are equal, the translation of the plural has the key "<text>#pl". */
  NT.tp = function (n, uno, altri, params) {
    const sing = NT.lingua === 'fr' ? Math.abs(n) < 2 : n === 1;
    const p = Object.assign({ n: n }, params);
    if (NT.lingua === 'en') return sostituisci(sing ? uno : altri, p);
    return NT.t(sing ? uno : (altri === uno ? uno + '#pl' : altri), p);
  };

  /* Translates a text that comes from the Python program (already composed, in English) or that was saved
     by an earlier version (in Italian). It does not complain when it finds nothing: it may be a name typed
     by the user or the text of a technical error. */
  let schemi = null, vecchi = null, schemiVecchi = null;
  const resa = (chiave, params) => sostituisci(NT.lingua === 'en' ? chiave : (DIZ[chiave] !== undefined ? DIZ[chiave] : chiave), params);
  function schema(forma, chiave) {
    const pezzi = forma.split(/\{(\w+)\}/);               // [text, name, text, name, ..., text]
    const nomi = [];
    let re = '^';
    pezzi.forEach((p, i) => {
      if (i % 2) { nomi.push(p); re += '([\\s\\S]+?)'; }
      else re += p.replace(/[.*+?^$()|[\]\\{}]/g, '\\$&');
    });
    return { chiave: chiave, nomi: nomi, re: new RegExp(re + '$'), fisso: pezzi.filter((p, i) => i % 2 === 0).join('').length };
  }
  function costruisciSchemi() {
    schemi = []; schemiVecchi = []; vecchi = {};
    for (const chiave in IT) {
      if (/\{\w+\}/.test(chiave)) schemi.push(schema(chiave, chiave));
      const it = IT[chiave];
      if (/\{\w+\}/.test(it)) schemiVecchi.push(schema(it, chiave));
      else if (!(it in vecchi)) vecchi[it] = chiave;
    }
    const piuSpecifico = (a, b) => b.fisso - a.fisso;       // the most specific shapes first
    schemi.sort(piuSpecifico); schemiVecchi.sort(piuSpecifico);
  }
  function cercaSchema(lista, testo) {
    for (const s of lista) {
      const m = s.re.exec(testo);
      if (!m) continue;
      const params = {};
      s.nomi.forEach((nome, i) => { params[nome] = NT.tr(m[i + 1]); });
      return resa(s.chiave, params);
    }
    return null;
  }
  NT.tr = function (testo) {
    if (testo === null || testo === undefined || testo === '') return testo;
    testo = String(testo);
    if (!schemi) costruisciSchemi();
    if (Object.prototype.hasOwnProperty.call(IT, testo)) return resa(testo);              // an English text of the program
    let r = cercaSchema(schemi, testo);                                                    // ... with variable values
    if (r !== null) return r;
    if (Object.prototype.hasOwnProperty.call(vecchi, testo)) return resa(vecchi[testo]);  // Italian text saved by an old version
    r = cercaSchema(schemiVecchi, testo);
    if (r !== null) return r;
    if (testo.indexOf('; ') > 0) {                                                         // several messages joined by "; "
      const parti = testo.split('; '), tradotte = parti.map(NT.tr);
      if (tradotte.some((x, i) => x !== parti[i])) return tradotte.join('; ');
    }
    return testo;
  };

  /* ---------- numbers and dates in the format of the language ---------- */
  const SEP = NT.lingua === 'en' ? '.' : ',';
  const MESI_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const LOCALI = { it: 'it-IT', en: 'en-GB', fr: 'fr-FR', de: 'de-DE', es: 'es-ES' };
  NT.locale = LOCALI[NT.lingua];
  NT.num = (n, dec) => (n === null || n === undefined) ? '' : Number(n).toFixed(dec === undefined ? 1 : dec).replace('.', SEP);
  NT.perc = v => v === null || v === undefined ? '' : (v * 100).toFixed(v >= 0.995 || v < 0.01 ? 1 : 0).replace('.', SEP) + '%';
  NT.migliaia = n => Number(n).toLocaleString(NT.locale);
  /* 'YYYY-MM-DD' -> 08/11/2026 (it, fr, es), 08.11.2026 (de), 8 Nov 2026 (en) */
  NT.fmtData = iso => {
    if (!iso) return '';
    const [a, m, g] = iso.slice(0, 10).split('-');
    if (NT.lingua === 'en') return String(+g) + ' ' + MESI_EN[+m - 1] + ' ' + a;
    return g + (NT.lingua === 'de' ? '.' + m + '.' : '/' + m + '/') + a;
  };
  NT.fmtDataOra = iso => iso ? NT.fmtData(iso) + ' ' + String(iso).slice(11, 16) : '';
  /* day and month without the year: 08/11, 08.11., 8 Nov */
  NT.fmtGiornoMese = iso => {
    if (!iso) return '';
    const [, m, g] = iso.slice(0, 10).split('-');
    if (NT.lingua === 'en') return String(+g) + ' ' + MESI_EN[+m - 1];
    return g + (NT.lingua === 'de' ? '.' + m + '.' : '/' + m);
  };
  NT.fraseGiorni = g => g === null || g === undefined ? '' : g <= 0 ? NT.t('today') : g === 1 ? NT.t('yesterday')
    : g < 60 ? NT.t('{n} days ago', { n: g })
      : g < 700 ? NT.t('{n} months ago', { n: Math.round(g / 30.4) })
        : NT.tp(Math.round(g / 365), '{n} year ago', '{n} years ago');
})();
