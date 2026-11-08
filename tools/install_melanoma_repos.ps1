<#
.SYNOPSIS
  Clona e installa su Windows i 5 repository di rilevamento del melanoma.

.DESCRIPTION
  - Ogni repository va in una cartella con prefisso del proprietario (evita il conflitto di nomi
    tra "Melanoma-Detection" e "melanoma-detection", uguali su Windows).
  - Ogni progetto Python ha un ambiente virtuale locale in .venv.
  - Correzione automatica di Streamlit\app.py in vatsal30 (riga showfileUploaderEncoding).
  - Lo script e' rieseguibile: se un repo esiste gia', fa solo un pull e completa l'installazione.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install_melanoma_repos.ps1
  powershell -ExecutionPolicy Bypass -File .\install_melanoma_repos.ps1 -Root D:\progetti\melanoma
#>
param(
    [string]$Root = (Join-Path $env:USERPROFILE 'melanoma-repos')
)

$ErrorActionPreference = 'Stop'
$Root = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Root)   # percorso assoluto anche se passato relativo
$results = [ordered]@{}
$PyExe  = $null
$PyArgs = @()

# ---------------------------------------------------------------- funzioni di supporto

function Write-Step([string]$Message) {
    Write-Host ''
    Write-Host "=== $Message" -ForegroundColor Cyan
}

function Test-Cmd([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# Esegue un comando nativo, mostra l'output e lancia un errore se il codice di uscita non e' 0.
function Invoke-Native {
    param([string]$Exe, [string[]]$ArgList)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @ArgList | Out-Host
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $old
    }
    if ($code -ne 0) {
        throw "Comando fallito (codice $code): $Exe $($ArgList -join ' ')"
    }
}

# Cerca Python 3.12 (preferito), poi 3.11, poi 3.10. Restituisce @{Exe=..; Args=..} oppure $null.
function Find-Python {
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if (Test-Cmd 'py') {
            foreach ($v in '3.12', '3.11', '3.10') {
                & py "-$v" --version 2>&1 | Out-Null
                if ($LASTEXITCODE -eq 0) { return @{ Exe = 'py'; Args = @("-$v"); Version = $v } }
            }
        }
        if (Test-Cmd 'python') {
            $out = (& python --version 2>&1 | Out-String)
            if ($out -match 'Python 3\.(10|11|12)\.') {
                return @{ Exe = 'python'; Args = @(); Version = ($out.Trim()) }
            }
        }
    } finally {
        $ErrorActionPreference = $old
    }
    return $null
}

# Clona il repository (o lo aggiorna se esiste gia'). Restituisce il percorso locale.
function Get-Repo([string]$Url, [string]$FolderName) {
    $dir = Join-Path $Root $FolderName
    if (Test-Path (Join-Path $dir '.git')) {
        Write-Host "Repository gia' presente, aggiorno: $dir"
        try {
            Invoke-Native 'git' @('-C', $dir, 'pull', '--ff-only')
        } catch {
            Write-Warning "git pull non riuscito (probabili modifiche locali): proseguo con la copia esistente."
        }
    } else {
        Invoke-Native 'git' @('clone', $Url, $dir)
    }
    return $dir
}

# Crea (se manca) l'ambiente virtuale .venv nella cartella indicata. Restituisce il python del venv.
function New-Venv([string]$Dir) {
    $venv = Join-Path $Dir '.venv'
    $py   = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path $py)) {
        Invoke-Native $PyExe ($PyArgs + @('-m', 'venv', $venv))
    }
    Invoke-Native $py @('-m', 'pip', 'install', '--upgrade', 'pip')
    return $py
}

function Invoke-Project([string]$Label, [scriptblock]$Body) {
    Write-Step $Label
    try {
        & $Body
        $results[$Label] = 'OK'
    } catch {
        $results[$Label] = "ERRORE: $($_.Exception.Message)"
        Write-Warning $_.Exception.Message
    }
}

# ---------------------------------------------------------------- prerequisiti

Write-Step 'Verifica prerequisiti'
$problems = @()

if (-not (Test-Cmd 'git')) {
    $problems += 'Git mancante          ->  winget install Git.Git'
} else {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & git lfs version 2>&1 | Out-Null
    $lfsOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    if (-not $lfsOk) { $problems += 'Git LFS mancante      ->  winget install GitHub.GitLFS' }
}

$py = Find-Python
if ($null -eq $py) {
    $problems += 'Python 3.10-3.12 mancante  ->  winget install Python.Python.3.12'
} else {
    $PyExe  = $py.Exe
    $PyArgs = $py.Args
    Write-Host "Python trovato: $($py.Exe) $($py.Args -join ' ') ($($py.Version))"
}

if (-not (Test-Cmd 'npm.cmd')) {
    $problems += 'Node.js/npm mancante  ->  winget install OpenJS.NodeJS.LTS'
}

if ($problems.Count -gt 0) {
    Write-Host ''
    Write-Host 'Mancano dei prerequisiti. Installali, apri un nuovo terminale e rilancia lo script:' -ForegroundColor Yellow
    $problems | ForEach-Object { Write-Host "  - $_" }
    exit 1
}

New-Item -ItemType Directory -Force -Path $Root | Out-Null
Write-Host "Cartella di destinazione: $Root"

# ---------------------------------------------------------------- 1/5 Melanoma-Detection_App

Invoke-Project '1/5 DeborahAdedigba - Melanoma-Detection_App (Streamlit + TensorFlow)' {
    $dir = Get-Repo 'https://github.com/DeborahAdedigba/Melanoma-Detection_App.git' 'DeborahAdedigba_Melanoma-Detection_App'

    # I modelli .keras / .h5 sono su Git LFS
    Invoke-Native 'git' @('lfs', 'install')
    Invoke-Native 'git' @('-C', $dir, 'lfs', 'pull')
    $stub = Get-ChildItem -Path $dir -Recurse -Include '*.keras', '*.h5' | Where-Object { $_.Length -lt 1024 }
    if ($stub) {
        Write-Warning "Alcuni modelli sono ancora segnaposto LFS (<1 KB): $(($stub | ForEach-Object Name) -join ', ')"
    }

    $venvPy = New-Venv $dir
    Invoke-Native $venvPy @('-m', 'pip', 'install', '-r', (Join-Path $dir 'requirements.txt'))
}

# ---------------------------------------------------------------- 2/5 skinsense

Invoke-Project '2/5 soureshmondal - skinsense (frontend Next.js)' {
    $dir = Get-Repo 'https://github.com/soureshmondal/skinsense.git' 'soureshmondal_skinsense'
    Push-Location (Join-Path $dir 'frontend')
    try {
        Invoke-Native 'npm.cmd' @('install', '--legacy-peer-deps', '--no-audit', '--no-fund')
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------- 3/5 Melanoma-Detector

Invoke-Project '3/5 VukIG - Melanoma-Detector (server FastAPI + client Expo)' {
    $dir = Get-Repo 'https://github.com/VukIG/Melanoma-Detector.git' 'VukIG_Melanoma-Detector'

    # Server: versioni non fissate (le versioni pinned del repo sono vecchie)
    $srv    = Join-Path $dir 'server'
    $venvPy = New-Venv $srv
    Invoke-Native $venvPy @('-m', 'pip', 'install', 'fastapi', 'uvicorn[standard]', 'pillow', 'numpy', 'pydantic', 'requests', 'python-multipart')
    New-Item -ItemType Directory -Force -Path (Join-Path $srv 'images') | Out-Null   # il server salva qui le foto

    # Client React Native / Expo
    Push-Location (Join-Path $dir 'client')
    try {
        Invoke-Native 'npm.cmd' @('install', '--legacy-peer-deps', '--no-audit', '--no-fund')
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------- 4/5 vatsal30 Melanoma-Detection

Invoke-Project '4/5 vatsal30 - Melanoma-Detection (PyTorch + Streamlit)' {
    $dir    = Get-Repo 'https://github.com/vatsal30/Melanoma-Detection.git' 'vatsal30_Melanoma-Detection'
    $venvPy = New-Venv $dir

    # Il requirements.txt originale (Python 3.7, torch 1.6, 2020) non e' installabile oggi:
    # uso pacchetti recenti, tranne wtfml 0.0.2 che il codice richiede (la 0.0.3 ha rinominato ClassificationLoader).
    Invoke-Native $venvPy @('-m', 'pip', 'install', 'torch', 'torchvision')
    Invoke-Native $venvPy @('-m', 'pip', 'install', 'streamlit', 'pandas', 'numpy', 'pillow', 'matplotlib', 'seaborn',
                            'plotly', 'chart-studio', 'cufflinks', 'scikit-learn', 'albumentations',
                            'pretrainedmodels', 'wtfml', 'opencv-python-headless')
    Invoke-Native $venvPy @('-m', 'pip', 'install', '--no-deps', 'wtfml==0.0.2')

    # Correzione di Streamlit\app.py: l'opzione 'deprecation.showfileUploaderEncoding' non esiste piu'
    $app = Join-Path $dir 'Streamlit\app.py'
    $txt = [System.IO.File]::ReadAllText($app)
    $pattern = '(?m)^([ \t]*)st\.set_option\(''deprecation\.showfileUploaderEncoding'', False\)'
    if ($txt -match $pattern) {
        $repl = '$1# st.set_option(''deprecation.showfileUploaderEncoding'', False)  # rimosso: opzione eliminata nelle versioni recenti di Streamlit'
        $new  = [regex]::Replace($txt, $pattern, $repl)
        [System.IO.File]::WriteAllText($app, $new, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host 'app.py corretto: riga showfileUploaderEncoding commentata.'
    } else {
        Write-Host 'app.py: nessuna correzione necessaria (gia'' applicata o riga assente).'
    }
}

# ---------------------------------------------------------------- 5/5 ukalwa (Android)

Invoke-Project '5/5 ukalwa - melanoma-detection (progetto Android Studio, solo clone)' {
    $dir = Get-Repo 'https://github.com/ukalwa/melanoma-detection.git' 'ukalwa_melanoma-detection'
    Write-Host "Clonato in $dir. La compilazione richiede Android Studio e OpenCV Android SDK 3.2.0 (vedi istruzioni sotto)."
}

# ---------------------------------------------------------------- riepilogo

Write-Step 'Riepilogo'
foreach ($k in $results.Keys) {
    $color = 'Green'
    if ($results[$k] -ne 'OK') { $color = 'Red' }
    Write-Host ("{0,-85} {1}" -f $k, $results[$k]) -ForegroundColor $color
}

Write-Host @"

------------------------------------------------------------------------------
COME AVVIARLI   (cartella base: $Root)
------------------------------------------------------------------------------
1) Melanoma-Detection_App
     cd $Root\DeborahAdedigba_Melanoma-Detection_App
     .\.venv\Scripts\python.exe -m streamlit run Melanoma_Detection.py

2) skinsense  (usa il servizio online souresh-skin-lesion-detection.hf.space:
              le immagini caricate vengono inviate a quel server)
     cd $Root\soureshmondal_skinsense\frontend
     npm.cmd run dev          ->  http://localhost:3000

3) Melanoma-Detector
     Server:  cd $Root\VukIG_Melanoma-Detector\server
              .\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
     Client:  cd $Root\VukIG_Melanoma-Detector\client
              npx.cmd expo start --tunnel      (poi scansiona il QR con Expo Go)
     ATTENZIONE: il client invia a http://192.168.1.172:8000/predict1 (IP fisso, endpoint
     inesistente nel server). Modifica client\src\context\ImageContext.jsx; il server
     e' un abbozzo e non contiene alcun modello.

4) vatsal30 Melanoma-Detection
     cd $Root\vatsal30_Melanoma-Detection\Streamlit
     ..\.venv\Scripts\python.exe -m streamlit run app.py
     Per le predizioni servono model\model_fold_0..4.bin, assenti dal repo: vanno addestrati
     (dataset Kaggle SIIM-ISIC in data\, poi resize_images.py, create_folds.py, train.py).

5) ukalwa melanoma-detection   (cartella: $Root\ukalwa_melanoma-detection)
     Non esiste un APK pronto: va compilato sul PC con gli strumenti dell'epoca (2017-2019).
     - Android Studio 3.3.x, NON l'ultima versione: https://developer.android.com/studio/archive
     - NDK r17c (gli NDK piu' recenti non supportano gnustl_static):
       https://github.com/android/ndk/wiki/Unsupported-Downloads
     - OpenCV Android SDK 3.2.0, poi variabile d'ambiente OPENCV_ANDROID_SDK sulla cartella estratta:
       https://sourceforge.net/projects/opencvlibrary/files/opencv-android/3.2.0/opencv-3.2.0-android-sdk.zip/download
     - Copia %OPENCV_ANDROID_SDK%\sdk\native\libs in app\src\main\jniLibs e imposta ndk.dir in local.properties
     - Android Studio: Build > Build APK(s). L'APK e' in app\build\outputs\apk\debug
     Passi completi (installazione sul telefono compresa) nella guida, sezione "Strumento 5".

Strumenti didattici e di ricerca, non diagnostici.
------------------------------------------------------------------------------
"@
