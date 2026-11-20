# Creates the "NeoTracker" icon on the Desktop; it opens the program in its own window, with no black console window.
# Run it by double-clicking Crea_scorciatoia_Desktop.bat (you do not need to open this file).
$ErrorActionPreference = 'Stop'

# The folder this file is in (neotracker.py is there too).
$cartella  = $PSScriptRoot
$programma = Join-Path $cartella 'neotracker.py'
$icona     = Join-Path $cartella 'Analizza_neo.ico'
if (-not (Test-Path $programma)) { throw "neotracker.py is missing in $cartella" }

# 1) Look for the "windowless" Python: pyw.exe (installed together with py.exe) or pythonw.exe.
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
    throw "Neither pyw.exe nor pythonw.exe was found: is Python installed? (https://www.python.org/downloads/)"
}

# 2) Create the shortcut on the Desktop (also when the Desktop is synchronised with OneDrive).
$desktop = [Environment]::GetFolderPath('Desktop')
$percorsoLnk = Join-Path $desktop 'NeoTracker.lnk'
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($percorsoLnk)
$lnk.TargetPath = $esegui
$lnk.Arguments = $argomenti
$lnk.WorkingDirectory = $cartella
if (Test-Path $icona) { $lnk.IconLocation = "$icona,0" }
$lnk.Description = 'NeoTracker: mole map, photo history, analysis, literature, UV index'
$lnk.Save()
Write-Host ('Icon created: ' + $percorsoLnk)
Write-Host ('  launches: ' + $esegui + ' ' + $argomenti)

# 3) If the old "Analizza neo" icon exists (the one that opened the black console window), remove it
#    ONLY if it really points to Analizza_neo.bat: this way no duplicate is left.
$vecchio = Join-Path $desktop 'Analizza neo.lnk'
if (Test-Path $vecchio) {
    $v = $shell.CreateShortcut($vecchio)
    if ($v.TargetPath -like '*Analizza_neo.bat') {
        Remove-Item $vecchio -Force
        Write-Host 'Removed the old "Analizza neo" icon ("NeoTracker" replaces it).'
    }
}
