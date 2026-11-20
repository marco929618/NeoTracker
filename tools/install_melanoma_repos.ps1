<#
.SYNOPSIS
  Clones and installs on Windows the 5 melanoma-detection repositories.

.DESCRIPTION
  - Each repository goes into a folder prefixed with the owner's name (avoids the name clash
    between "Melanoma-Detection" and "melanoma-detection", which are the same on Windows).
  - Each Python project gets a local virtual environment in .venv.
  - Automatic fix of Streamlit\app.py in vatsal30 (showfileUploaderEncoding line).
  - The script can be re-run: if a repo already exists, it only does a pull and completes the installation.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install_melanoma_repos.ps1
  powershell -ExecutionPolicy Bypass -File .\install_melanoma_repos.ps1 -Root D:\progetti\melanoma
#>
param(
    [string]$Root = (Join-Path $env:USERPROFILE 'melanoma-repos')
)

$ErrorActionPreference = 'Stop'
$Root = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Root)   # absolute path even when a relative one is passed
$results = [ordered]@{}
$PyExe  = $null
$PyArgs = @()

# ---------------------------------------------------------------- helper functions

function Write-Step([string]$Message) {
    Write-Host ''
    Write-Host "=== $Message" -ForegroundColor Cyan
}

function Test-Cmd([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# Runs a native command, shows the output and raises an error if the exit code is not 0.
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
        throw "Command failed (code $code): $Exe $($ArgList -join ' ')"
    }
}

# Looks for Python 3.12 (preferred), then 3.11, then 3.10. Returns @{Exe=..; Args=..} or $null.
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

# Clones the repository (or updates it if it already exists). Returns the local path.
function Get-Repo([string]$Url, [string]$FolderName) {
    $dir = Join-Path $Root $FolderName
    if (Test-Path (Join-Path $dir '.git')) {
        Write-Host "Repository already present, updating: $dir"
        try {
            Invoke-Native 'git' @('-C', $dir, 'pull', '--ff-only')
        } catch {
            Write-Warning "git pull failed (probably local changes): continuing with the existing copy."
        }
    } else {
        Invoke-Native 'git' @('clone', $Url, $dir)
    }
    return $dir
}

# Creates (if missing) the .venv virtual environment in the given folder. Returns the venv's python.
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
        $results[$Label] = "ERROR: $($_.Exception.Message)"
        Write-Warning $_.Exception.Message
    }
}

# ---------------------------------------------------------------- prerequisites

Write-Step 'Checking prerequisites'
$problems = @()

if (-not (Test-Cmd 'git')) {
    $problems += 'Git missing            ->  winget install Git.Git'
} else {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & git lfs version 2>&1 | Out-Null
    $lfsOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    if (-not $lfsOk) { $problems += 'Git LFS missing        ->  winget install GitHub.GitLFS' }
}

$py = Find-Python
if ($null -eq $py) {
    $problems += 'Python 3.10-3.12 missing  ->  winget install Python.Python.3.12'
} else {
    $PyExe  = $py.Exe
    $PyArgs = $py.Args
    Write-Host "Python found: $($py.Exe) $($py.Args -join ' ') ($($py.Version))"
}

if (-not (Test-Cmd 'npm.cmd')) {
    $problems += 'Node.js/npm missing    ->  winget install OpenJS.NodeJS.LTS'
}

if ($problems.Count -gt 0) {
    Write-Host ''
    Write-Host 'Some prerequisites are missing. Install them, open a new terminal and run the script again:' -ForegroundColor Yellow
    $problems | ForEach-Object { Write-Host "  - $_" }
    exit 1
}

New-Item -ItemType Directory -Force -Path $Root | Out-Null
Write-Host "Destination folder: $Root"

# ---------------------------------------------------------------- 1/5 Melanoma-Detection_App

Invoke-Project '1/5 DeborahAdedigba - Melanoma-Detection_App (Streamlit + TensorFlow)' {
    $dir = Get-Repo 'https://github.com/DeborahAdedigba/Melanoma-Detection_App.git' 'DeborahAdedigba_Melanoma-Detection_App'

    # The .keras / .h5 models are on Git LFS
    Invoke-Native 'git' @('lfs', 'install')
    Invoke-Native 'git' @('-C', $dir, 'lfs', 'pull')
    $stub = Get-ChildItem -Path $dir -Recurse -Include '*.keras', '*.h5' | Where-Object { $_.Length -lt 1024 }
    if ($stub) {
        Write-Warning "Some models are still LFS placeholders (<1 KB): $(($stub | ForEach-Object Name) -join ', ')"
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

    # Server: unpinned versions (the repo's pinned versions are old)
    $srv    = Join-Path $dir 'server'
    $venvPy = New-Venv $srv
    Invoke-Native $venvPy @('-m', 'pip', 'install', 'fastapi', 'uvicorn[standard]', 'pillow', 'numpy', 'pydantic', 'requests', 'python-multipart')
    New-Item -ItemType Directory -Force -Path (Join-Path $srv 'images') | Out-Null   # the server saves the photos here

    # React Native / Expo client
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

    # The original requirements.txt (Python 3.7, torch 1.6, 2020) cannot be installed today:
    # use recent packages, except wtfml 0.0.2 which the code requires (0.0.3 renamed ClassificationLoader).
    Invoke-Native $venvPy @('-m', 'pip', 'install', 'torch', 'torchvision')
    Invoke-Native $venvPy @('-m', 'pip', 'install', 'streamlit', 'pandas', 'numpy', 'pillow', 'matplotlib', 'seaborn',
                            'plotly', 'chart-studio', 'cufflinks', 'scikit-learn', 'albumentations',
                            'pretrainedmodels', 'wtfml', 'opencv-python-headless')
    Invoke-Native $venvPy @('-m', 'pip', 'install', '--no-deps', 'wtfml==0.0.2')

    # Fix for Streamlit\app.py: the 'deprecation.showfileUploaderEncoding' option no longer exists
    $app = Join-Path $dir 'Streamlit\app.py'
    $txt = [System.IO.File]::ReadAllText($app)
    $pattern = '(?m)^([ \t]*)st\.set_option\(''deprecation\.showfileUploaderEncoding'', False\)'
    if ($txt -match $pattern) {
        $repl = '$1# st.set_option(''deprecation.showfileUploaderEncoding'', False)  # removed: option dropped in recent Streamlit versions'
        $new  = [regex]::Replace($txt, $pattern, $repl)
        [System.IO.File]::WriteAllText($app, $new, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host 'app.py fixed: showfileUploaderEncoding line commented out.'
    } else {
        Write-Host 'app.py: no fix needed (already applied or line absent).'
    }
}

# ---------------------------------------------------------------- 5/5 ukalwa (Android)

Invoke-Project '5/5 ukalwa - melanoma-detection (Android Studio project, clone only)' {
    $dir = Get-Repo 'https://github.com/ukalwa/melanoma-detection.git' 'ukalwa_melanoma-detection'
    Write-Host "Cloned into $dir. Building requires Android Studio and OpenCV Android SDK 3.2.0 (see the instructions below)."
}

# ---------------------------------------------------------------- summary

Write-Step 'Summary'
foreach ($k in $results.Keys) {
    $color = 'Green'
    if ($results[$k] -ne 'OK') { $color = 'Red' }
    Write-Host ("{0,-85} {1}" -f $k, $results[$k]) -ForegroundColor $color
}

Write-Host @"

------------------------------------------------------------------------------
HOW TO RUN THEM   (base folder: $Root)
------------------------------------------------------------------------------
1) Melanoma-Detection_App
     cd $Root\DeborahAdedigba_Melanoma-Detection_App
     .\.venv\Scripts\python.exe -m streamlit run Melanoma_Detection.py

2) skinsense  (uses the online service souresh-skin-lesion-detection.hf.space:
              uploaded images are sent to that server)
     cd $Root\soureshmondal_skinsense\frontend
     npm.cmd run dev          ->  http://localhost:3000

3) Melanoma-Detector
     Server:  cd $Root\VukIG_Melanoma-Detector\server
              .\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
     Client:  cd $Root\VukIG_Melanoma-Detector\client
              npx.cmd expo start --tunnel      (then scan the QR code with Expo Go)
     WARNING: the client posts to http://192.168.1.172:8000/predict1 (fixed IP, endpoint
     that does not exist in the server). Edit client\src\context\ImageContext.jsx; the server
     is a stub and contains no model.

4) vatsal30 Melanoma-Detection
     cd $Root\vatsal30_Melanoma-Detection\Streamlit
     ..\.venv\Scripts\python.exe -m streamlit run app.py
     Predictions need model\model_fold_0..4.bin, which are missing from the repo: they must be trained
     (Kaggle SIIM-ISIC dataset in data\, then resize_images.py, create_folds.py, train.py).

5) ukalwa melanoma-detection   (folder: $Root\ukalwa_melanoma-detection)
     There is no ready-made APK: it must be built on the PC with the tools of the time (2017-2019).
     - Android Studio 3.3.x, NOT the latest version: https://developer.android.com/studio/archive
     - NDK r17c (newer NDKs do not support gnustl_static):
       https://github.com/android/ndk/wiki/Unsupported-Downloads
     - OpenCV Android SDK 3.2.0, then set the OPENCV_ANDROID_SDK environment variable to the extracted folder:
       https://sourceforge.net/projects/opencvlibrary/files/opencv-android/3.2.0/opencv-3.2.0-android-sdk.zip/download
     - Copy %OPENCV_ANDROID_SDK%\sdk\native\libs to app\src\main\jniLibs and set ndk.dir in local.properties
     - Android Studio: Build > Build APK(s). The APK is in app\build\outputs\apk\debug
     Full steps (including installation on the phone) are in the guide, section "Tool 5".

Educational and research tools, not diagnostic.
------------------------------------------------------------------------------
"@
