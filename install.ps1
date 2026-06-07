# Clear host and set standard error preference
$ErrorActionPreference = "Stop"

# Helper logging functions with colors
function Log-Info ($Message) {
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Log-Success ($Message) {
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Log-Warning ($Message) {
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Log-Error ($Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "          spotify-dl Installer Tool (Windows)     " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Verify Windows OS
if (-not $IsWindows -and $env:OS -ne "Windows_NT") {
    Log-Error "This script is designed for Windows operating systems."
    exit 1
}

# Check administrator execution level
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Log-Warning "This script is not running as Administrator."
    Log-Warning "Updating the System PATH (Machine level) and installing system applications require administrator privileges."
    Log-Warning "Please run this script in an Administrator PowerShell window."
}

# Helper to download files
function Download-File ($Url, $OutFile) {
    Log-Info "Downloading $Url..."
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
}

# Helper to permanently append a directory to the System PATH env variable (Machine level)
function Add-To-System-Path ($DirToAppend) {
    try {
        $currentPath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        $normDir = $DirToAppend.TrimEnd('\')
        $splitPaths = $currentPath -split ';' | ForEach-Object { $_.Trim().TrimEnd('\') }
        if ($splitPaths -notcontains $normDir) {
            $newPath = "$currentPath;$normDir"
            [System.Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
            Log-Success "Added '$normDir' to System PATH permanently."
        }
    } catch {
        Log-Warning "Could not update System PATH environment variable permanently (requires Administrator elevation): $_"
    }
}

# 2. Check/Install Python (preferably >= 3.11)
$installPython = $false
$pythonCmd = "python"

if (Get-Command "python" -ErrorAction SilentlyContinue) {
    try {
        $versionStr = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        [version]$version = $versionStr
        if ($version -lt [version]"3.11") {
            Log-Warning "Found Python $versionStr, but version 3.11+ is required."
            $installPython = $true
        } else {
            Log-Info "Python $versionStr is already installed (meets requirements)."
        }
    } catch {
        Log-Warning "Python command is available, but could not determine version. Reinstalling Python 3.11..."
        $installPython = $true
    }
} else {
    Log-Info "Python is not installed."
    $installPython = $true
}

if ($installPython) {
    Log-Info "Installing Python 3.11..."
    $installerPath = Join-Path $env:TEMP "python-3.11-installer.exe"
    Download-File "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" $installerPath
    
    Log-Info "Running Python installer silently (user-only)..."
    $proc = Start-Process -FilePath $installerPath -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1" -Wait -PassThru
    if ($proc.ExitCode -eq 0) {
        Log-Success "Successfully installed Python 3.11."
    } else {
        Log-Error "Failed to install Python 3.11 (exit code: $($proc.ExitCode))."
        exit 1
    }
}

# Find Python executable path if it was just installed and is not in PATH yet
# And ensure it's permanently set in System Path
$pythonPath = (Get-Command "python" -ErrorAction SilentlyContinue).Source
if ($pythonPath -and $pythonPath -notlike "*WindowsApps*") {
    $pythonDir = Split-Path $pythonPath
    $scriptsDir = Join-Path $pythonDir "Scripts"
    $env:PATH = "$pythonDir;$scriptsDir;$env:PATH"
    Add-To-System-Path $pythonDir
    Add-To-System-Path $scriptsDir
} else {
    $localPythonDirs = Join-Path $env:USERPROFILE "AppData\Local\Programs\Python"
    if (Test-Path $localPythonDirs) {
        $pythonExe = Get-ChildItem -Path $localPythonDirs -Filter "python.exe" -Recurse | Select-Object -First 1
        if ($pythonExe) {
            $pythonCmd = $pythonExe.FullName
            Log-Info "Found Python path: $pythonCmd"
            $pythonDir = Split-Path $pythonCmd
            $scriptsDir = Join-Path $pythonDir "Scripts"
            $env:PATH = "$pythonDir;$scriptsDir;$env:PATH"
            Add-To-System-Path $pythonDir
            Add-To-System-Path $scriptsDir
        }
    }
}

# 3. Check/Install Node.js 20+
$installNode = $false
if (Get-Command "node" -ErrorAction SilentlyContinue) {
    try {
        $nodeVersion = (& node -v).TrimStart('v')
        $nodeMajor = [int]($nodeVersion.Split('.')[0])
        if ($nodeMajor -lt 20) {
            Log-Warning "Found Node.js version v$nodeVersion, but Node.js 20+ is required."
            $installNode = $true
        } else {
            Log-Info "Node.js v$nodeVersion (>= 20) is already installed."
        }
    } catch {
        Log-Warning "Node command is available, but could not determine version. Reinstalling Node.js 20+..."
        $installNode = $true
    }
} else {
    Log-Info "Node.js is not installed."
    $installNode = $true
}

if ($installNode) {
    Log-Info "Installing Node.js 20..."
    $nodeMsiPath = Join-Path $env:TEMP "node-installer.msi"
    Download-File "https://nodejs.org/dist/v20.12.2/node-v20.12.2-x64.msi" $nodeMsiPath
    
    Log-Info "Running Node.js installer silently..."
    $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$nodeMsiPath`" /qn /norestart" -Wait -PassThru
    if ($proc.ExitCode -eq 0) {
        Log-Success "Successfully installed Node.js 20."
        $nodeDir = "C:\Program Files\nodejs"
        if (Test-Path $nodeDir) {
            $env:PATH = "$nodeDir;$env:PATH"
            Add-To-System-Path $nodeDir
        }
    } else {
        Log-Error "Failed to install Node.js 20 (exit code: $($proc.ExitCode))."
        exit 1
    }
}

# Ensure Node is in current PATH and System PATH
$nodePath = (Get-Command "node" -ErrorAction SilentlyContinue).Source
if ($nodePath) {
    $nodeDir = Split-Path $nodePath
    $env:PATH = "$nodeDir;$env:PATH"
    Add-To-System-Path $nodeDir
} else {
    $nodeDir = "C:\Program Files\nodejs"
    if (Test-Path $nodeDir) {
        $env:PATH = "$nodeDir;$env:PATH"
        Add-To-System-Path $nodeDir
    }
}

# 4. Check/Install FFmpeg (required for downloading and conversion)
if (Get-Command "ffmpeg" -ErrorAction SilentlyContinue) {
    Log-Info "ffmpeg is already installed."
    # Even if installed, ensure it is permanently in System PATH
    $ffmpegPath = (Get-Command "ffmpeg").Source
    $ffmpegBinPath = Split-Path $ffmpegPath
    Add-To-System-Path $ffmpegBinPath
} else {
    Log-Info "ffmpeg is not installed. Installing FFmpeg..."
    $ffmpegZip = Join-Path $env:TEMP "ffmpeg.zip"
    Download-File "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" $ffmpegZip
    
    Log-Info "Extracting FFmpeg..."
    $ffmpegDestDir = Join-Path $env:USERPROFILE "AppData\Local\ffmpeg"
    if (Test-Path $ffmpegDestDir) {
        Remove-Item -Path $ffmpegDestDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Force -Path $ffmpegDestDir | Out-Null
    
    Expand-Archive -Path $ffmpegZip -DestinationPath $ffmpegDestDir -Force
    
    # Locate Gyan's bin folder
    $binFolder = Get-ChildItem -Path $ffmpegDestDir -Filter "bin" -Recurse | Select-Object -First 1
    if ($binFolder) {
        $ffmpegBinPath = $binFolder.FullName
        Log-Info "FFmpeg bin path: $ffmpegBinPath"
        
        # Add permanently to System Path
        Add-To-System-Path $ffmpegBinPath
        $env:PATH = "$ffmpegBinPath;$env:PATH"
    } else {
        Log-Warning "Could not find bin directory in FFmpeg archive. Manual installation may be required."
    }
}

# 5. Check/Install pipx
if (-not (Get-Command "pipx" -ErrorAction SilentlyContinue)) {
    Log-Info "pipx is not installed. Installing pipx..."
    & $pythonCmd -m pip install --user pipx
    & $pythonCmd -m pipx ensurepath --force | Out-Null
    
    # Prepend scripts folder to PATH for current session and System Path
    $userScriptsDir = & $pythonCmd -c "import sysconfig; print(sysconfig.get_path('scripts', 'user'))"
    if (Test-Path $userScriptsDir) {
        $env:PATH = "$userScriptsDir;$env:PATH"
        Add-To-System-Path $userScriptsDir
    }
    
    if (-not (Get-Command "pipx" -ErrorAction SilentlyContinue)) {
        Log-Error "pipx was installed but could not be found on PATH."
        exit 1
    }
    Log-Success "Successfully installed pipx."
} else {
    Log-Info "pipx is already installed."
}

# Make sure local bin folder is in PATH and System PATH (where pipx apps are saved)
$pipxBin = Join-Path $env:USERPROFILE ".local\bin"
if (Test-Path $pipxBin) {
    $env:PATH = "$pipxBin;$env:PATH"
    Add-To-System-Path $pipxBin
}

# 6. Install/Upgrade spotify-dl using pipx
Log-Info "Installing/upgrading spotify-dl using pipx..."
$list = & pipx list
if ($list -like "*spotify-dl*") {
    Log-Info "spotify-dl is already installed. Running pipx upgrade..."
    & pipx upgrade spotify-dl
} else {
    & pipx install git+https://github.com/SouravDutta2206/spotify-dl.git
    if ($LASTEXITCODE -ne 0 -and -not $?) {
        Log-Error "Failed to install spotify-dl via pipx."
        exit 1
    }
    Log-Success "spotify-dl has been successfully installed!"
}

# 7. Print setup instructions
Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "                  INSTALLATION COMPLETED SUCCESSFULLY!                " -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "spotify-dl has been successfully installed using pipx."
Write-Host ""
Write-Host "To configure and authenticate spotify-dl, follow these steps:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Get Spotify API Credentials:"
Write-Host "     Go to https://developer.spotify.com/dashboard, log in, create an app,"
Write-Host "     and retrieve your Client ID and Client Secret."
Write-Host ""
Write-Host "  2. Save your credentials in spotify-dl configuration:"
Write-Host "     spotify-dl config set client-id <YOUR_CLIENT_ID>" -ForegroundColor Yellow
Write-Host "     spotify-dl config set client-secret <YOUR_CLIENT_SECRET>" -ForegroundColor Yellow
Write-Host ""
Write-Host "  3. Authenticate with Spotify:"
Write-Host "     spotify-dl auth login" -ForegroundColor Yellow
Write-Host ""
Write-Host "  4. Start downloading tracks, albums, or playlists:"
Write-Host "     spotify-dl https://open.spotify.com/track/..." -ForegroundColor Yellow
Write-Host ""
Write-Host "IMPORTANT: If the 'spotify-dl' command is not recognized, please restart" -ForegroundColor Yellow
Write-Host "your terminal session or command prompt."
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""
