# SPDX-License-Identifier: GPL-3.0-or-later
# NeoTracker - Copyright (C) 2026 gli autori di NeoTracker.
# Software libero: puoi ridistribuirlo e/o modificarlo secondo i termini della GNU General Public License
# versione 3 o successiva. Nessuna garanzia, nemmeno di idoneità a uno scopo (vedi il file LICENSE).
"""
Controllo delle traduzioni di NeoTracker.

Come funziona il sistema (dettagli in CONTRIBUTING.md):
  - Il testo ITALIANO è l'originale e fa da chiave. Nel codice JavaScript si scrive NT.t('Salva neo');
    nel codice Python i testi destinati all'utente sono segnati con T("...").
  - Le traduzioni stanno in web/i18n_en.js, i18n_fr.js, i18n_de.js, i18n_es.js: un dizionario
    {"testo italiano": "traduzione"} per lingua.

Questo programma:
  1. raccoglie dal codice tutti i testi italiani da tradurre;
  2. controlla che ogni dizionario li contenga tutti, che nessuna traduzione sia vuota e che i segnaposto
     ({n}, {nome}, ...) siano gli stessi dell'originale;
  3. controlla i testi delle finestrelle di avvio (TESTI_AVVIO in src/90_main.py).

Uso (dalla cartella del progetto):
  python3 tools/traduzioni.py                  controlla tutto (esce con errore se qualcosa non va)
  python3 tools/traduzioni.py --elenco         stampa tutti i testi italiani da tradurre
  python3 tools/traduzioni.py --mancano fr     stampa, in formato dizionario, i testi che mancano in francese
  python3 tools/traduzioni.py --italiano       cerca nel JavaScript frasi italiane non segnate (può dare falsi allarmi)

build.py esegue lo stesso controllo: una traduzione mancante blocca la costruzione di neotracker.py.
"""
import ast
import json
import re
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
FILE_PY = sorted((RADICE / "src").glob("*.py")) + [RADICE / "melanoma_batch.py"]
# i18n.js (il motore) contiene a sua volta testi da tradurre; i18n_xx.js sono i dizionari e non si leggono
FILE_JS = sorted(f for f in (RADICE / "web").glob("*.js") if not re.fullmatch(r"i18n_[a-z]{2}\.js", f.name))
SEGNAPOSTO = re.compile(r"\{(\w+)\}")


def lingue():
    """Le lingue dichiarate in src/00_head.py (LINGUE = ("it", "en", ...))."""
    albero = ast.parse((RADICE / "src" / "00_head.py").read_text(encoding="utf-8"))
    for n in ast.walk(albero):
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "LINGUE" for t in n.targets):
            return list(ast.literal_eval(n.value))
    raise SystemExit("LINGUE non trovata in src/00_head.py")


# ---------------------------------------------------------------------------------------------
# Raccolta dei testi dal codice Python
# ---------------------------------------------------------------------------------------------
def _msgid_da_nodo(nodo, errori, dove):
    """Il testo italiano contenuto in T(...): una stringa semplice oppure una f-string (le espressioni
    semplici diventano segnaposto con lo stesso nome; quelle complesse vanno riscritte con .format)."""
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
                    errori.append(f"{dove}: espressione troppo complessa dentro T(f\"...\"): "
                                  f"usa T(\"... {{nome}} ...\").format(nome=...)")
                    return None
        return "".join(pezzi)
    errori.append(f"{dove}: T() vuole un testo scritto per esteso (non una variabile)")
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
                    errori.append(f"{dove}: il messaggio di {nome} non è segnato con T()")
    return trovati


def testi_avvio():
    """TESTI_AVVIO di src/90_main.py: {testo italiano: {lingua: testo}}."""
    albero = ast.parse((RADICE / "src" / "90_main.py").read_text(encoding="utf-8"))
    for n in ast.walk(albero):
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TESTI_AVVIO" for t in n.targets):
            return ast.literal_eval(n.value)
    return {}


# ---------------------------------------------------------------------------------------------
# Raccolta dei testi dal codice JavaScript
# ---------------------------------------------------------------------------------------------
_ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


def _stringa_js(s, i):
    """Legge il testo tra apici che comincia in s[i] (' oppure "). Restituisce (valore, indice dopo l'apice finale) o None."""
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
    """s[i] è la '(' di una chiamata: restituisce la lista degli argomenti di primo livello (come testo grezzo)."""
    prof, j, inizio, args = 0, i, i + 1, []
    while j < len(s):
        c = s[j]
        if c in "'\"":
            r = _stringa_js(s, j)
            j = r[1] if r else j + 1
            continue
        if c == "`":                                   # template literal: lo salto per intero
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
    """Se 'testo' è una sola stringa JavaScript (con eventuali spazi attorno) ne restituisce il valore."""
    t = testo.strip()
    r = _stringa_js(t, 0) if t else None
    return r[0] if r and r[1] == len(t) else None


def raccogli_js(errori):
    trovati = {}

    def aggiungi(m, f, riga):
        trovati.setdefault(m, []).append(f"{f.relative_to(RADICE)}:{riga}")

    for f in FILE_JS:
        s = f.read_text(encoding="utf-8")
        if f.name == "i18n.js":        # l'intestazione di i18n.js contiene esempi d'uso nei commenti: non sono testi dell'app
            s = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), s, flags=re.S)
        riga = lambda pos: s.count("\n", 0, pos) + 1                       # noqa: E731
        for m in re.finditer(r"\bNT\.(t|m|tp)\(", s):
            args = _argomenti(s, m.end() - 1)
            if m.group(1) in ("t", "m"):
                v = _solo_stringa(args[0]) if args else None
                if v is not None:
                    aggiungi(v, f, riga(m.start()))
                # NT.t(variabile) è ammesso: la variabile viene da una tabella segnata con NT.m / NT.t
            else:
                if len(args) < 3:
                    errori.append(f"{f.name}:{riga(m.start())}: NT.tp() vuole (n, singolare, plurale)")
                    continue
                uno, altri = _solo_stringa(args[1]), _solo_stringa(args[2])
                if uno is None or altri is None:
                    errori.append(f"{f.name}:{riga(m.start())}: NT.tp(): singolare e plurale devono essere testi scritti per esteso")
                    continue
                aggiungi(uno, f, riga(m.start()))
                aggiungi(altri + "#pl" if altri == uno else altri, f, riga(m.start()))
    # Nomi delle regioni del corpo: body.js li compone da coppia('Nome','m|f') / singola('Nome')
    corpo = (RADICE / "web" / "body.js").read_text(encoding="utf-8")
    for m in re.finditer(r"\bcoppia\('([^']+)',\s*'([mf])'", corpo):
        suff = "a" if m.group(2) == "f" else "o"
        for lato in ("destr", "sinistr"):
            aggiungi(f"{m.group(1)} {lato}{suff}", RADICE / "web" / "body.js", corpo.count("\n", 0, m.start()) + 1)
    for m in re.finditer(r"\bsingola\('([^']+)'", corpo):
        aggiungi(m.group(1), RADICE / "web" / "body.js", corpo.count("\n", 0, m.start()) + 1)
    return trovati


# ---------------------------------------------------------------------------------------------
# Dizionari
# ---------------------------------------------------------------------------------------------
def carica_dizionario(lingua, errori):
    f = RADICE / "web" / f"i18n_{lingua}.js"
    if not f.exists():
        errori.append(f"manca il file {f.relative_to(RADICE)}")
        return {}
    s = f.read_text(encoding="utf-8")
    m = re.search(r"\.%s\s*=\s*\{" % re.escape(lingua), s)
    if not m:
        errori.append(f"{f.name}: formato non riconosciuto (atteso: ....{lingua} = {{ ... }};)")
        return {}
    try:
        d, _ = json.JSONDecoder().raw_decode(s[m.end() - 1:])
    except ValueError as e:
        errori.append(f"{f.name}: il dizionario non è un JSON valido ({e})")
        return {}
    return d


def scrivi_dizionario(lingua, d):
    """Scrive web/i18n_<lingua>.js nel formato che build.py e il browser leggono (ordinato, una voce per riga)."""
    righe = ",\n".join("  %s: %s" % (json.dumps(k, ensure_ascii=False), json.dumps(v, ensure_ascii=False)) for k, v in sorted(d.items()))
    testo = ("/* Traduzioni dell'interfaccia di NeoTracker: %s. Chiave = testo italiano originale.\n"
             "   I segnaposto {nome} vanno lasciati uguali. Controllo: python3 tools/traduzioni.py */\n"
             "(window.NT_DIZIONARI = window.NT_DIZIONARI || {}).%s = {\n%s\n};\n") % (lingua, lingua, righe)
    (RADICE / "web" / f"i18n_{lingua}.js").write_text(testo, encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Controlli
# ---------------------------------------------------------------------------------------------
def segnaposto(testo):
    return sorted(SEGNAPOSTO.findall(testo))


def controlla(stampa=print):
    """Restituisce (errori, avvisi)."""
    errori, avvisi = [], []
    ling = lingue()
    altre = [l for l in ling if l != "it"]
    testi = {}
    for sorgente in (raccogli_python(errori), raccogli_js(errori)):
        for k, v in sorgente.items():
            testi.setdefault(k, []).extend(v)

    # elenco delle lingue coerente tra Python, JavaScript e pagina
    js = (RADICE / "web" / "i18n.js").read_text(encoding="utf-8")
    m = re.search(r"NT\.LINGUE\s*=\s*\[(.*?)\];", js, re.S)
    if not m or re.findall(r"\['(\w+)',", m.group(1)) != ling:
        errori.append(f"l'elenco NT.LINGUE di web/i18n.js non coincide con LINGUE di src/00_head.py {ling}")
    pagina = (RADICE / "web" / "index.html").read_text(encoding="utf-8")
    for l in altre:
        if f'src="/i18n_{l}.js"' not in pagina:
            errori.append(f"web/index.html non carica i18n_{l}.js")

    for l in altre:
        d = carica_dizionario(l, errori)
        if not d:
            continue
        for k, dove in sorted(testi.items()):
            base = k[:-3] if k.endswith("#pl") else k
            if k not in d:
                errori.append(f"[{l}] manca la traduzione di «{base}»{' (plurale)' if k.endswith('#pl') else ''}  ({dove[0]})")
                continue
            v = d[k]
            if not isinstance(v, str) or not v.strip():
                errori.append(f"[{l}] traduzione vuota per «{base}»")
            elif segnaposto(v) != segnaposto(base):
                errori.append(f"[{l}] segnaposto diversi per «{base}»: originale {segnaposto(base)}, traduzione {segnaposto(v)}")
            elif "\n" in base and "\n" not in v:
                avvisi.append(f"[{l}] «{base[:40]}…» va a capo nell'originale ma non nella traduzione")
        inutili = sorted(set(d) - set(testi))
        if inutili:
            avvisi.append(f"[{l}] {len(inutili)} voci non più usate nel codice, per esempio «{inutili[0][:50]}»")

    # finestrelle di avvio
    for k, per_lingua in testi_avvio().items():
        for l in altre:
            v = per_lingua.get(l)
            if not v or not v.strip():
                errori.append(f"TESTI_AVVIO: manca «{k[:40]}» in {l}")
            elif segnaposto(v) != segnaposto(k):
                errori.append(f"TESTI_AVVIO [{l}]: segnaposto diversi per «{k[:40]}»")
    return errori, avvisi, testi


# ---------------------------------------------------------------------------------------------
# Ricerca (facoltativa) di frasi italiane non segnate nel JavaScript
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
                        # è dentro NT.t(...)/NT.m(...)/NT.tp(...) o in un commento? salto se la riga lo contiene
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
    if "--italiano" in argv:
        for r in cerca_italiano():
            print(r)
        return 0
    errori, avvisi, testi = controlla()
    if "--elenco" in argv:
        for k in sorted(testi):
            print(k)
        return 0
    if "--mancano" in argv:
        l = argv[argv.index("--mancano") + 1]
        d = carica_dizionario(l, [])
        print("{")
        for k in sorted(testi):
            if k not in d:
                print("  %s: \"\"," % json.dumps(k, ensure_ascii=False))
        print("}")
        return 0
    for a in avvisi:
        print("avviso:", a)
    for e in errori:
        print("ERRORE:", e)
    if errori:
        print(f"\n{len(errori)} problemi nelle traduzioni. Dettagli: python3 tools/traduzioni.py")
        return 1
    print(f"Traduzioni OK: {len(testi)} testi in {len(lingue()) - 1} lingue.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
