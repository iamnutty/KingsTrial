# PowerShell Code Signing Script for KingsTrial

# Self-Signed Certificate Creation
# Run as Administrator

Write-Host "KingsTrial Code Signing Setup" -ForegroundColor Green
Write-Host "==============================" -ForegroundColor Green
Write-Host ""

# Check if running as admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator" -ForegroundColor Red
    Write-Host "Please run PowerShell as Administrator and try again."
    exit 1
}

# Option 1: Create Self-Signed Certificate
Write-Host "Creating self-signed code signing certificate..." -ForegroundColor Cyan
$cert = New-SelfSignedCertificate `
    -CertStoreLocation cert:\LocalMachine\My `
    -Subject "CN=KingsTrial Developer" `
    -Type CodeSigningCert `
    -NotAfter (Get-Date).AddYears(5)

Write-Host "Certificate created successfully!" -ForegroundColor Green
Write-Host "Thumbprint: $($cert.Thumbprint)" -ForegroundColor Yellow
Write-Host ""

# Move to Trusted Root
Write-Host "Adding to Trusted Root Certificate Store..." -ForegroundColor Cyan
$rootStore = [System.Security.Cryptography.X509Certificates.X509Store]::new("Root", "LocalMachine")
$rootStore.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
$rootStore.Add($cert)
$rootStore.Close()

Write-Host "Certificate added to trusted root!" -ForegroundColor Green
Write-Host ""

# Sign the executable if it exists
$exePath = ".\dist\KingsTrial.exe"
if (Test-Path $exePath) {
    Write-Host "Found KingsTrial.exe - signing now..." -ForegroundColor Cyan
    
    Set-AuthenticodeSignature -FilePath $exePath `
        -Certificate $cert `
        -TimestampServer "http://timestamp.sectigo.com" `
        -HashAlgorithm SHA256 | Out-Null
    
    $signature = Get-AuthenticodeSignature $exePath
    if ($signature.Status -eq "Valid") {
        Write-Host "Signature applied successfully!" -ForegroundColor Green
        Write-Host "Status: $($signature.Status)" -ForegroundColor Green
        Write-Host "Signer: $($signature.SignerCertificate.Subject)" -ForegroundColor Green
    } else {
        Write-Host "Signature verification failed!" -ForegroundColor Red
        Write-Host "Status: $($signature.Status)" -ForegroundColor Red
    }
} else {
    Write-Host "WARNING: dist/KingsTrial.exe not found" -ForegroundColor Yellow
    Write-Host "Build the executable first using build.ps1" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Run build.ps1 to create the executable"
Write-Host "2. Run this script again to sign it (or it will auto-sign if exe exists)"
Write-Host "3. Run build-installer.ps1 to create the installer"
Write-Host ""
