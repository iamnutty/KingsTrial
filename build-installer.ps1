# Build Installer Script for KingsTrial using NSIS
# Requires NSIS to be installed

Write-Host "KingsTrial Installer Build" -ForegroundColor Green
Write-Host "==========================" -ForegroundColor Green
Write-Host ""

# Check if NSIS is installed
$nsisPath = "C:\Program Files (x86)\NSIS\makensis.exe"
if (-not (Test-Path $nsisPath)) {
    Write-Host "ERROR: NSIS is not installed" -ForegroundColor Red
    Write-Host ""
    Write-Host "To install NSIS:" -ForegroundColor Cyan
    Write-Host "1. Download from: https://nsis.sourceforge.io/Download"
    Write-Host "2. Run the installer with default settings"
    Write-Host "3. Run this script again"
    Write-Host ""
    exit 1
}

# Check if executable exists
if (-not (Test-Path ".\dist\KingsTrial.exe")) {
    Write-Host "ERROR: dist/KingsTrial.exe not found" -ForegroundColor Red
    Write-Host "Please run build.ps1 first to create the executable"
    exit 1
}

# Build the installer
Write-Host "Building installer with NSIS..." -ForegroundColor Cyan
& $nsisPath ".\installer.nsi"

if ($LASTEXITCODE -eq 0) {
    $installerPath = ".\KingsTrial-Installer.exe"
    if (Test-Path $installerPath) {
        $fileSize = (Get-Item $installerPath).Length / 1MB
        Write-Host ""
        Write-Host "Installer created successfully!" -ForegroundColor Green
        Write-Host "Output: $installerPath" -ForegroundColor Yellow
        Write-Host "Size: $([Math]::Round($fileSize, 2)) MB" -ForegroundColor Yellow
    }
} else {
    Write-Host "Installer build failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
