# SPDX-License-Identifier: GPL-3.0-or-later
# NeoTracker - Copyright (C) 2026 gli autori di NeoTracker.
# Software libero: puoi ridistribuirlo e/o modificarlo secondo i termini della GNU General Public License
# versione 3 o successiva. Nessuna garanzia, nemmeno di idoneità a uno scopo (vedi il file LICENSE).
# NON è un dispositivo medico e non fa diagnosi: vedi DISCLAIMER.md.
# Costruisce neotracker.py (il programma da eseguire) unendo i pezzi src/*.py e incorporando le pagine web (web/*).
import base64
import importlib.util
import py_compile
import sys
from pathlib import Path

radice = Path(__file__).resolve().parent

# ---- controllo delle traduzioni: se un testo non ha la traduzione in tutte le lingue, non si costruisce nulla ----
_spec = importlib.util.spec_from_file_location("traduzioni", radice / "tools" / "traduzioni.py")
_traduzioni = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_traduzioni)
_errori, _avvisi, _testi = _traduzioni.controlla()
for _a in _avvisi:
    print("avviso:", _a)
if _errori:
    for _e in _errori:
        print("ERRORE:", _e)
    sys.exit(f"Costruzione interrotta: {len(_errori)} problemi nelle traduzioni (vedi sopra; dettagli con: python3 tools/traduzioni.py)")
print(f"Traduzioni OK: {len(_testi)} testi in {len(_traduzioni.lingue()) - 1} lingue.")
tipi = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".ico": "image/x-icon", ".png": "image/png"}

pezzi = []
for f in sorted((radice / "src").glob("*.py")):
    if f.name.startswith("90_"):
        continue
    pezzi.append(f.read_text(encoding="utf-8").rstrip() + "\n")

# ---- pagine web incorporate (leggibili, in stringhe "raw") ----
web = ["\n# ==========================================================================================",
       "# 6d. PAGINE WEB (HTML / CSS / JavaScript) incorporate in questo file",
       "# ==========================================================================================",
       "# Se vuoi modificare l'aspetto dell'app puoi cambiare anche il testo qui sotto.",
       ""]
for f in sorted((radice / "web").iterdir()):
    if f.suffix == ".png":
        # Le immagini sono binarie: le incorporiamo come testo base64 (righe da 100 caratteri)
        # e il programma le riconverte in byte all'avvio con base64.b64decode.
        b64 = base64.b64encode(f.read_bytes()).decode("ascii")
        righe = "\n".join(b64[i:i + 100] for i in range(0, len(b64), 100))
        nome_var = f"_WEB_{f.stem.upper()}_{f.suffix[1:].upper()}_B64"
        web.append(f"{nome_var} = \"\"\"\n{righe}\n\"\"\"")
        web.append(f'WEB_FILES["/{f.name}"] = ("{tipi[f.suffix]}", base64.b64decode({nome_var}))')
        web.append("")
        continue
    testo = f.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "'''" not in testo, f"{f.name} contiene ''' : non incorporabile"
    assert not testo.rstrip("\n").endswith("\\"), f"{f.name} finisce con backslash"
    chiave = "/" + f.name
    web.append(f"_WEB_{f.stem.upper()}_{f.suffix[1:].upper()} = r'''{testo}'''")
    web.append(f'WEB_FILES["{chiave}"] = ("{tipi[f.suffix]}", _WEB_{f.stem.upper()}_{f.suffix[1:].upper()}.encode("utf-8"))')
    web.append("")
pezzi.append("\n".join(web) + "\n")

for f in sorted((radice / "src").glob("90_*.py")):
    pezzi.append(f.read_text(encoding="utf-8").rstrip() + "\n")

out = radice / "neotracker.py"
out.write_bytes("\n".join(pezzi).encode("utf-8"))      # byte esatti: righe sempre con "\n" (anche su Windows) e valido da Python 3.9
py_compile.compile(str(out), doraise=True)
print(f"OK: {out} ({out.stat().st_size // 1024} KB, {len(out.read_text(encoding='utf-8').splitlines())} righe)")
