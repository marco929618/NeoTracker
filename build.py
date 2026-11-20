# SPDX-License-Identifier: GPL-3.0-or-later
# NeoTracker - Copyright (C) 2026 the NeoTracker authors.
# Free software: you can redistribute it and/or modify it under the terms of the GNU General Public License
# version 3 or later. No warranty, not even of fitness for a purpose (see the LICENSE file).
# NOT a medical device and it does not diagnose: see DISCLAIMER.md.
# Builds neotracker.py (the program to run) by joining the src/*.py pieces and embedding the web pages (web/*).
import base64
import importlib.util
import py_compile
import sys
from pathlib import Path

radice = Path(__file__).resolve().parent

# ---- translation check: if a text has no translation in every language, nothing is built ----
_spec = importlib.util.spec_from_file_location("traduzioni", radice / "tools" / "traduzioni.py")
_traduzioni = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_traduzioni)
_errori, _avvisi, _testi = _traduzioni.controlla()
for _a in _avvisi:
    print("warning:", _a)
if _errori:
    for _e in _errori:
        print("ERROR:", _e)
    sys.exit(f"Build stopped: {len(_errori)} problems in the translations (see above; details with: python3 tools/traduzioni.py)")
print(f"Translations OK: {len(_testi)} texts in {len(_traduzioni.lingue()) - 1} languages.")
tipi = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".ico": "image/x-icon", ".png": "image/png"}

pezzi = []
for f in sorted((radice / "src").glob("*.py")):
    if f.name.startswith("90_"):
        continue
    pezzi.append(f.read_text(encoding="utf-8").rstrip() + "\n")

# ---- pagine web incorporate (leggibili, in stringhe "raw") ----
web = ["\n# ==========================================================================================",
       "# 6d. WEB PAGES (HTML / CSS / JavaScript) embedded in this file",
       "# ==========================================================================================",
       "# If you want to change the look of the app you can also change the text below.",
       ""]
for f in sorted((radice / "web").iterdir()):
    if f.suffix == ".png":
        # The images are binary: we embed them as base64 text (lines of 100 characters) and the program
        # converts them back to bytes at start-up with base64.b64decode.
        b64 = base64.b64encode(f.read_bytes()).decode("ascii")
        righe = "\n".join(b64[i:i + 100] for i in range(0, len(b64), 100))
        nome_var = f"_WEB_{f.stem.upper()}_{f.suffix[1:].upper()}_B64"
        web.append(f"{nome_var} = \"\"\"\n{righe}\n\"\"\"")
        web.append(f'WEB_FILES["/{f.name}"] = ("{tipi[f.suffix]}", base64.b64decode({nome_var}))')
        web.append("")
        continue
    testo = f.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "'''" not in testo, f"{f.name} contains ''' : cannot be embedded"
    assert not testo.rstrip("\n").endswith("\\"), f"{f.name} ends with a backslash"
    chiave = "/" + f.name
    web.append(f"_WEB_{f.stem.upper()}_{f.suffix[1:].upper()} = r'''{testo}'''")
    web.append(f'WEB_FILES["{chiave}"] = ("{tipi[f.suffix]}", _WEB_{f.stem.upper()}_{f.suffix[1:].upper()}.encode("utf-8"))')
    web.append("")
pezzi.append("\n".join(web) + "\n")

for f in sorted((radice / "src").glob("90_*.py")):
    pezzi.append(f.read_text(encoding="utf-8").rstrip() + "\n")

out = radice / "neotracker.py"
out.write_bytes("\n".join(pezzi).encode("utf-8"))      # exact bytes: lines always with "\n" (also on Windows) and valid from Python 3.9
py_compile.compile(str(out), doraise=True)
print(f"OK: {out} ({out.stat().st_size // 1024} KB, {len(out.read_text(encoding='utf-8').splitlines())} lines)")
