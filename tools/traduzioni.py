# SPDX-License-Identifier: GPL-3.0-or-later
# NeoTracker - Copyright (C) 2026 the NeoTracker authors.
# Free software: you can redistribute it and/or modify it under the terms of the GNU General Public License
# version 3 or later. No warranty, not even of fitness for a purpose (see the LICENSE file).
"""
Translation checker for NeoTracker.

How the system works (details in CONTRIBUTING.md):
  - The ENGLISH text is the original and acts as the key. In JavaScript code you write NT.t('Save mole');
    in Python code, user-facing texts are marked with T("...").
  - Translations live in web/i18n_it.js, i18n_fr.js, i18n_de.js, i18n_es.js: one dictionary
    {"English text": "translation"} per language. English itself needs no dictionary.

This program:
  1. collects every translatable English text from the code;
  2. checks that each dictionary contains all of them, that no translation is empty and that the
     placeholders ({n}, {name}, ...) are the same as in the original;
  3. checks the start-up window texts (TESTI_AVVIO in src/90_main.py).

Usage (from the project folder):
  python3 tools/traduzioni.py                  check everything (exits with an error if something is wrong)
  python3 tools/traduzioni.py --list           print every English text to translate
  python3 tools/traduzioni.py --missing fr     print, in dictionary format, the texts missing in French
  python3 tools/traduzioni.py --italian        look for unmarked Italian phrases in the JavaScript
                                               (may give false alarms)

build.py runs the same check: a missing translation stops neotracker.py from being built.
"""
import ast
import json
import re
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
FILE_PY = sorted((RADICE / "src").glob("*.py")) + [RADICE / "melanoma_batch.py"]
# i18n.js (the engine) contains texts to translate too; i18n_xx.js are the dictionaries and are not scanned
FILE_JS = sorted(f for f in (RADICE / "web").glob("*.js") if not re.fullmatch(r"i18n_[a-z]{2}\.js", f.name))
SEGNAPOSTO = re.compile(r"\{(\w+)\}")


def lingue():
    """The languages declared in src/00_head.py (LINGUE = ("en", "it", ...)); the first one is the source language."""
    albero = ast.parse((RADICE / "src" / "00_head.py").read_text(encoding="utf-8"))
    for n in ast.walk(albero):
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "LINGUE" for t in n.targets):
            return list(ast.literal_eval(n.value))
    raise SystemExit("LINGUE not found in src/00_head.py")


# ---------------------------------------------------------------------------------------------
# Collecting the texts from the Python code
# ---------------------------------------------------------------------------------------------
def _msgid_da_nodo(nodo, errori, dove):
    """The English text inside T(...): a plain string or an f-string (simple expressions become
    placeholders with the same name; complex ones must be rewritten with .format)."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.JoinedStr):
        pezzi = []
        for v in nodo.values:
            if isinstance(v, ast.Constant):
                pezzi.append(v.value)
            elif isinstance(v, ast.FormattedValue):
                e = v.value
                if isinstance(e, ast.Name):
                    pezzi.append("{" + e.id + "}")
                elif isinstance(e, ast.Attribute):
                    pezzi.append("{" + e.attr + "}")
                else:
                    errori.append(f"{dove}: expression too complex inside T(f\"...\"): "
                                  f"use T(\"... {{name}} ...\").format(name=...)")
                    return None
        return "".join(pezzi)
    errori.append(f"{dove}: T() needs a literal text (not a variable)")
    return None


def raccogli_python(errori):
    trovati = {}
    for f in FILE_PY:
        albero = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for n in ast.walk(albero):
            if not isinstance(n, ast.Call):
                continue
            nome = n.func.id if isinstance(n.func, ast.Name) else None
            dove = f"{f.relative_to(RADICE)}:{n.lineno}"
            if nome == "T" and n.args:
                m = _msgid_da_nodo(n.args[0], errori, dove)
                if m is not None:
                    trovati.setdefault(m, []).append(dove)
            elif nome in ("ErroreRichiesta", "ErroreServizio") and n.args:
                a = n.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and re.search(r"[a-zà-ù]{3} ", a.value):
                    errori.append(f"{dove}: the message of {nome} is not marked with T()")
    return trovati


def testi_avvio():
    """TESTI_AVVIO of src/90_main.py: {English text: {language: text}}."""
    albero = ast.parse((RADICE / "src" / "90_main.py").read_text(encoding="utf-8"))
    for n in ast.walk(albero):
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TESTI_AVVIO" for t in n.targets):
            return ast.literal_eval(n.value)
    return {}


# ---------------------------------------------------------------------------------------------
# Collecting the texts from the JavaScript code
# ---------------------------------------------------------------------------------------------
_ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


def _stringa_js(s, i):
    """Reads the quoted text that starts at s[i] (' or "). Returns (value, index after the closing quote) or None."""
    q = s[i]
    if q not in "'\"":
        return None
    out, j = [], i + 1
    while j < len(s):
        c = s[j]
        if c == "\\":
            d = s[j + 1]
            if d == "u":
                out.append(chr(int(s[j + 2:j + 6], 16)))
                j += 6
                continue
            if d == "x":
                out.append(chr(int(s[j + 2:j + 4], 16)))
                j += 4
                continue
            out.append(_ESC.get(d, d))
            j += 2
            continue
        if c == q:
            return "".join(out), j + 1
        if c == "\n":
            return None
        out.append(c)
        j += 1
    return None


def _argomenti(s, i):
    """s[i] is the '(' of a call: returns the list of top-level arguments (as raw text)."""
    prof, j, inizio, args = 0, i, i + 1, []
    while j < len(s):
        c = s[j]
        if c in "'\"":
            r = _stringa_js(s, j)
            j = r[1] if r else j + 1
            continue
        if c == "`":                                   # template literal: skipped as a whole
            j = s.find("`", j + 1) + 1 or len(s)
            continue
        if c in "([{":
            prof += 1
        elif c in ")]}":
            prof -= 1
            if prof == 0:
                args.append(s[inizio:j])
                return args
        elif c == "," and prof == 1:
            args.append(s[inizio:j])
            inizio = j + 1
        j += 1
    return args


def _solo_stringa(testo):
    """If 'testo' is a single JavaScript string (with optional spaces around it) returns its value."""
    t = testo.strip()
    r = _stringa_js(t, 0) if t else None
    return r[0] if r and r[1] == len(t) else None


def raccogli_js(errori):
    trovati = {}

    def aggiungi(m, f, riga):
        trovati.setdefault(m, []).append(f"{f.relative_to(RADICE)}:{riga}")

    for f in FILE_JS:
        s = f.read_text(encoding="utf-8")
        if f.name == "i18n.js":        # the header of i18n.js contains usage examples in comments: they are not app texts
            s = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), s, flags=re.S)
        riga = lambda pos: s.count("\n", 0, pos) + 1                       # noqa: E731
        for m in re.finditer(r"\bNT\.(t|m|tp)\(", s):
            args = _argomenti(s, m.end() - 1)
            if m.group(1) in ("t", "m"):
                v = _solo_stringa(args[0]) if args else None
                if v is not None:
                    aggiungi(v, f, riga(m.start()))
                # NT.t(variable) is allowed: the variable comes from a table marked with NT.m / NT.t
            else:
                if len(args) < 3:
                    errori.append(f"{f.name}:{riga(m.start())}: NT.tp() needs (n, singular, plural)")
                    continue
                uno, altri = _solo_stringa(args[1]), _solo_stringa(args[2])
                if uno is None or altri is None:
                    errori.append(f"{f.name}:{riga(m.start())}: NT.tp(): singular and plural must be literal texts")
                    continue
                aggiungi(uno, f, riga(m.start()))
                aggiungi(altri + "#pl" if altri == uno else altri, f, riga(m.start()))
    # Body region names: body.js builds them from coppia('Name', poly) / singola('Name', poly)
    corpo = (RADICE / "web" / "body.js").read_text(encoding="utf-8")
    for m in re.finditer(r"\bcoppia\('([^']+)'", corpo):
        for lato in ("right", "left"):
            aggiungi(f"{m.group(1)}, {lato}", RADICE / "web" / "body.js", corpo.count("\n", 0, m.start()) + 1)
    for m in re.finditer(r"\bsingola\('([^']+)'", corpo):
        aggiungi(m.group(1), RADICE / "web" / "body.js", corpo.count("\n", 0, m.start()) + 1)
    return trovati


# ---------------------------------------------------------------------------------------------
# Dictionaries
# ---------------------------------------------------------------------------------------------
def carica_dizionario(lingua, errori):
    f = RADICE / "web" / f"i18n_{lingua}.js"
    if not f.exists():
        errori.append(f"missing file {f.relative_to(RADICE)}")
        return {}
    s = f.read_text(encoding="utf-8")
    m = re.search(r"\.%s\s*=\s*\{" % re.escape(lingua), s)
    if not m:
        errori.append(f"{f.name}: unrecognised format (expected: ....{lingua} = {{ ... }};)")
        return {}
    try:
        d, _ = json.JSONDecoder().raw_decode(s[m.end() - 1:])
    except ValueError as e:
        errori.append(f"{f.name}: the dictionary is not valid JSON ({e})")
        return {}
    return d


def scrivi_dizionario(lingua, d):
    """Writes web/i18n_<lingua>.js in the format that build.py and the browser read (sorted, one entry per line)."""
    righe = ",\n".join("  %s: %s" % (json.dumps(k, ensure_ascii=False), json.dumps(v, ensure_ascii=False)) for k, v in sorted(d.items()))
    testo = ("/* NeoTracker interface translations: %s. Key = the English source text.\n"
             "   Keep the {name} placeholders unchanged. Check: python3 tools/traduzioni.py */\n"
             "(window.NT_DIZIONARI = window.NT_DIZIONARI || {}).%s = {\n%s\n};\n") % (lingua, lingua, righe)
    (RADICE / "web" / f"i18n_{lingua}.js").write_text(testo, encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------------
def segnaposto(testo):
    return sorted(SEGNAPOSTO.findall(testo))


def controlla(stampa=print):
    """Returns (errors, warnings, texts)."""
    errori, avvisi = [], []
    ling = lingue()
    altre = [l for l in ling if l != ling[0]]       # every language except the source one (English)
    testi = {}
    for sorgente in (raccogli_python(errori), raccogli_js(errori)):
        for k, v in sorgente.items():
            testi.setdefault(k, []).extend(v)

    # the language list must agree between Python, JavaScript and the page
    js = (RADICE / "web" / "i18n.js").read_text(encoding="utf-8")
    m = re.search(r"NT\.LINGUE\s*=\s*\[(.*?)\];", js, re.S)
    if not m or re.findall(r"\['(\w+)',", m.group(1)) != ling:
        errori.append(f"the NT.LINGUE list of web/i18n.js does not match LINGUE of src/00_head.py {ling}")
    pagina = (RADICE / "web" / "index.html").read_text(encoding="utf-8")
    for l in altre:
        if f'src="/i18n_{l}.js"' not in pagina:
            errori.append(f"web/index.html does not load i18n_{l}.js")

    for l in altre:
        d = carica_dizionario(l, errori)
        if not d:
            continue
        for k, dove in sorted(testi.items()):
            base = k[:-3] if k.endswith("#pl") else k
            if k not in d:
                errori.append(f"[{l}] missing translation of «{base}»{' (plural)' if k.endswith('#pl') else ''}  ({dove[0]})")
                continue
            v = d[k]
            if not isinstance(v, str) or not v.strip():
                errori.append(f"[{l}] empty translation for «{base}»")
            elif segnaposto(v) != segnaposto(base):
                errori.append(f"[{l}] different placeholders for «{base}»: original {segnaposto(base)}, translation {segnaposto(v)}")
            elif "\n" in base and "\n" not in v:
                avvisi.append(f"[{l}] «{base[:40]}…» has a line break in the original but not in the translation")
        inutili = sorted(set(d) - set(testi))
        if inutili:
            avvisi.append(f"[{l}] {len(inutili)} entries no longer used in the code, for example «{inutili[0][:50]}»")

    # start-up windows
    for k, per_lingua in testi_avvio().items():
        for l in altre:
            v = per_lingua.get(l)
            if not v or not v.strip():
                errori.append(f"TESTI_AVVIO: missing «{k[:40]}» in {l}")
            elif segnaposto(v) != segnaposto(k):
                errori.append(f"TESTI_AVVIO [{l}]: different placeholders for «{k[:40]}»")
    return errori, avvisi, testi


# ---------------------------------------------------------------------------------------------
# Optional search for unmarked Italian phrases in the JavaScript
# ---------------------------------------------------------------------------------------------
_PAROLE_IT = re.compile(r"\b(il|lo|la|le|gli|di|del|della|dei|delle|che|per|non|un|una|con|nel|nella|nei|sono|è|hai|ho|più|come|anche|solo|tutti|tutte|ogni|quando|dove)\b|[àèéìòù]")


def cerca_italiano():
    risultati = []
    for f in FILE_JS:
        s = f.read_text(encoding="utf-8")
        i = 0
        while i < len(s):
            c = s[i]
            if c in "'\"":
                r = _stringa_js(s, i)
                if r:
                    v, fine = r
                    if " " in v and len(v) > 12 and _PAROLE_IT.search(v.lower()):
                        # is it inside NT.t(...)/NT.m(...)/NT.tp(...) or in a comment? skip if the line contains it
                        inizio_riga = s.rfind("\n", 0, i) + 1
                        riga = s[inizio_riga:s.find("\n", i)]
                        if not re.search(r"NT\.(t|m|tp)\(|window\.NT\.t\(|^\s*(//|\*|/\*)", riga) and "console." not in riga:
                            risultati.append(f"{f.name}:{s.count(chr(10), 0, i) + 1}: {v[:70]}")
                    i = fine
                    continue
            elif c == "/" and s[i:i + 2] == "//":
                i = s.find("\n", i) if s.find("\n", i) > 0 else len(s)
                continue
            elif c == "/" and s[i:i + 2] == "/*":
                i = s.find("*/", i) + 2 if s.find("*/", i) > 0 else len(s)
                continue
            i += 1
    return risultati


def main(argv):
    if "--italian" in argv:
        for r in cerca_italiano():
            print(r)
        return 0
    errori, avvisi, testi = controlla()
    if "--list" in argv:
        for k in sorted(testi):
            print(k)
        return 0
    if "--missing" in argv:
        l = argv[argv.index("--missing") + 1]
        d = carica_dizionario(l, [])
        print("{")
        for k in sorted(testi):
            if k not in d:
                print("  %s: \"\"," % json.dumps(k, ensure_ascii=False))
        print("}")
        return 0
    for a in avvisi:
        print("warning:", a)
    for e in errori:
        print("ERROR:", e)
    if errori:
        print(f"\n{len(errori)} problems in the translations. Details: python3 tools/traduzioni.py")
        return 1
    print(f"Translations OK: {len(testi)} texts in {len(lingue()) - 1} languages.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
