# Build script for KingsTrial executable
# This script creates a standalone executable using PyInstaller

Write-Host "Building KingsTrial executable..." -ForegroundColor Green
Write-Host ""

# Clean previous builds
if (Test-Path dist) {
    Remove-Item dist -Recurse -Force
    Write-Host "Cleaned dist folder"
}
if (Test-Path build) {
    Remove-Item build -Recurse -Force
    Write-Host "Cleaned build folder"
}
Get-ChildItem -Filter "*.spec" | Remove-Item -Force
Write-Host ""

# Run PyInstaller
Write-Host "Running PyInstaller..." -ForegroundColor Cyan
$pyInstallerArgs = @(
    "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    "--name", "KingsTrial",
    "--hidden-import=scenes",
    "--hidden-import=ai",
    "--hidden-import=ui",
    "--collect-all=pygame",
    "--add-data", "assets;assets",
    "--add-data", "config.json;.",
    "main.py"
)

& python $pyInstallerArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Build completed successfully!" -ForegroundColor Green
Write-Host "Executable created at: dist\KingsTrial.exe" -ForegroundColor Yellow
Write-Host ""
