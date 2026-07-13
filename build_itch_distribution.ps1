# build_itch_distribution.ps1
# ===========================
# King's Trial — Distribution Builder for itch.io and Steam.
#
# This script bundles the compiled standalone game executable with all
# necessary external folders and configurations (assets, themes, maps, sounds, 
# config.json, and the Stockfish AI engine) into a ready-to-distribute 
# 'itch' folder, and creates a zipped package for instant upload.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File build_itch_distribution.ps1
#

$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Magenta
Write-Host "     KING'S TRIAL — ITCH/STEAM DISTRIBUTOR" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Magenta
Write-Host ""

$RootPath = Get-Location
$ItchPath = Join-Path $RootPath "itch"
$DistExe = Join-Path $RootPath "dist\KingsTrial.exe"

# 1. Check if the PyInstaller build is already present, if not, compile it
if (-not (Test-Path $DistExe)) {
    Write-Host "[-] Compiled KingsTrial.exe not found at $DistExe." -ForegroundColor Yellow
    Write-Host "[*] Compiling game via build.ps1 first..." -ForegroundColor Cyan
    
    $BuildScript = Join-Path $RootPath "build.ps1"
    if (Test-Path $BuildScript) {
        powershell -ExecutionPolicy Bypass -File $BuildScript
    } else {
        Write-Error "build.ps1 script not found. Make sure you are in the project root."
    }

    if (-not (Test-Path $DistExe)) {
        Write-Error "PyInstaller build succeeded but KingsTrial.exe was not found at $DistExe."
    }
} else {
    Write-Host "[+] Found compiled KingsTrial.exe at $DistExe." -ForegroundColor Green
}

# 2. Clean up any existing 'itch' distribution directory and zip file
if (Test-Path $ItchPath) {
    Write-Host "[*] Cleaning old itch folder..." -ForegroundColor Cyan
    Remove-Item $ItchPath -Recurse -Force
}
$ZipPath = Join-Path $RootPath "KingsTrial_itch.zip"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}

# 3. Create the itch directory structure
Write-Host "[*] Creating itch/ distribution folder..." -ForegroundColor Cyan
New-Item -ItemType Directory -Path $ItchPath | Out-Null
New-Item -ItemType Directory -Path (Join-Path $ItchPath "saves") | Out-Null

# 4. Copy the compiled executable
Write-Host "[*] Copying KingsTrial.exe..." -ForegroundColor Cyan
Copy-Item $DistExe -Destination (Join-Path $ItchPath "KingsTrial.exe") -Force

# 5. Copy the Assets folder (themes, sounds, maps, fonts, etc.)
Write-Host "[*] Copying assets folder (themes, maps, sounds, fonts)..." -ForegroundColor Cyan
$SrcAssets = Join-Path $RootPath "assets"
if (Test-Path $SrcAssets) {
    Copy-Item $SrcAssets -Destination (Join-Path $ItchPath "assets") -Recurse -Force
} else {
    Write-Warning "Assets folder not found in project root!"
}

# 6. Copy the Stockfish binary folder
Write-Host "[*] Copying stockfish engine folder..." -ForegroundColor Cyan
$SrcStockfish = Join-Path $RootPath "stockfish"
if (Test-Path $SrcStockfish) {
    Copy-Item $SrcStockfish -Destination (Join-Path $ItchPath "stockfish") -Recurse -Force
} else {
    Write-Warning "Stockfish folder not found in project root!"
}

# 7. Copy the config file
Write-Host "[*] Copying config.json..." -ForegroundColor Cyan
$SrcConfig = Join-Path $RootPath "config.json"
if (Test-Path $SrcConfig) {
    Copy-Item $SrcConfig -Destination (Join-Path $ItchPath "config.json") -Force
} else {
    # Generate a default configuration file if missing
    $DefaultConfig = @{
        "single_player" = $false
        "human_colour" = "white"
        "neutral_ai" = "random"
        "opponent_ai" = "random"
        "time_control" = "5+10"
        "theme" = "default"
        "sfx_volume" = 2
        "music_volume" = 2
        "layout_file" = "TEST_CSV.csv"
        "relay_server_url" = "ws://localhost:8765"
    }
    $DefaultConfig | ConvertTo-Json | Out-File -FilePath (Join-Path $ItchPath "config.json") -Encoding utf8
}

# 8. Create compressed ZIP archive
Write-Host "[*] Compressing itch folder into KingsTrial_itch.zip..." -ForegroundColor Cyan
try {
    Compress-Archive -Path $ItchPath -DestinationPath $ZipPath -Force
    Write-Host "[+] Created KingsTrial_itch.zip successfully!" -ForegroundColor Green
} catch {
    Write-Warning "Failed to compress itch folder: $_"
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Magenta
Write-Host "  DISTRIBUTION PACKAGING COMPLETED SUCCESSFULLY!  " -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Magenta
Write-Host "  Standlone package  : $ItchPath" -ForegroundColor Yellow
Write-Host "  Zipped package     : $ZipPath" -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Magenta
Write-Host ""
