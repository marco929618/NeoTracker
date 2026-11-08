# Crea sul Desktop l'icona "NeoTracker" che apre il programma nella sua finestra, senza finestra nera.
# Si lancia con un doppio clic su Crea_scorciatoia_Desktop.bat (non serve aprire questo file).
$ErrorActionPreference = 'Stop'

# La cartella in cui si trova questo file (li' c'e' anche neotracker.py).
$cartella  = $PSScriptRoot
$programma = Join-Path $cartella 'neotracker.py'
$icona     = Join-Path $cartella 'Analizza_neo.ico'
if (-not (Test-Path $programma)) { throw "Manca neotracker.py in $cartella" }

# 1) Cerco il Python "senza finestra nera": pyw.exe (installato insieme a py.exe) oppure pythonw.exe.
$esegui = $null
$argomenti = $null
$pyw = Get-Command pyw.exe -ErrorAction SilentlyContinue
if ($pyw) {
    $esegui = $pyw.Source
    $argomenti = '-3 "' + $programma + '"'
} else {
    $pythonw = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($pythonw) {
        $esegui = $pythonw.Source
        $argomenti = '"' + $programma + '"'
    }
}
if (-not $esegui) {
    throw "Non trovo pyw.exe ne' pythonw.exe: Python e' installato? (https://www.python.org/downloads/)"
}

# 2) Creo il collegamento sul Desktop (anche se il Desktop e' sincronizzato con OneDrive).
$desktop = [Environment]::GetFolderPath('Desktop')
$percorsoLnk = Join-Path $desktop 'NeoTracker.lnk'
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($percorsoLnk)
$lnk.TargetPath = $esegui
$lnk.Arguments = $argomenti
$lnk.WorkingDirectory = $cartella
if (Test-Path $icona) { $lnk.IconLocation = "$icona,0" }
$lnk.Description = 'NeoTracker: mappa dei nei, storico foto, analisi, letteratura, indice UV'
$lnk.Save()
Write-Host ('Icona creata: ' + $percorsoLnk)
Write-Host ('  avvia: ' + $esegui + ' ' + $argomenti)

# 3) Se esiste la vecchia icona "Analizza neo" (quella che apriva la finestra nera), la tolgo
#    SOLO se punta davvero a Analizza_neo.bat: cosi' non resta un doppione.
$vecchio = Join-Path $desktop 'Analizza neo.lnk'
if (Test-Path $vecchio) {
    $v = $shell.CreateShortcut($vecchio)
    if ($v.TargetPath -like '*Analizza_neo.bat') {
        Remove-Item $vecchio -Force
        Write-Host 'Tolta la vecchia icona "Analizza neo" (ora c''e'' "NeoTracker").'
    }
}
