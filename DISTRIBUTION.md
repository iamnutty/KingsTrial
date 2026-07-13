# KingsTrial Distribution Guide

## Overview
This guide explains how to build and distribute KingsTrial as a standalone executable for Windows users.

## Prerequisites
- Python 3.8+ with Pygame installed
- PyInstaller (automatically installed via build scripts)
- NSIS (optional, for creating installer) - download from: https://nsis.sourceforge.io/

## Building the Executable

### Quick Build
Run the build script:

**PowerShell:**
```powershell
.\build.ps1
```

**Batch (CMD):**
```batch
build.bat
```

The executable will be created at: `dist\KingsTrial.exe`

**File Size:** ~51 MB (includes all dependencies)

## Testing the Executable

1. Navigate to the `dist` folder
2. Double-click `KingsTrial.exe`
3. The game should launch normally

## Creating an Installer

### Option 1: Using NSIS (Recommended)

1. **Install NSIS:**
   - Download from: https://nsis.sourceforge.io/Download
   - Run the installer with default settings

2. **Build the installer:**
   ```powershell
   # From the project root
   cd dist
   "C:\Program Files (x86)\NSIS\makensis.exe" ..\installer.nsi
   ```

3. **Output:** `KingsTrial-Installer.exe` in the project root

### Option 2: Using Inno Setup

Alternative installer framework - see `inno-setup-example.iss` for template.

## Distribution Options

### Option A: Direct EXE Distribution
- **File:** `dist/KingsTrial.exe`
- **Size:** ~51 MB
- **Pros:** Simple, no installation required
- **Cons:** Large file size
- **Best for:** Early access, beta testing

### Option B: Installer Distribution
- **File:** `KingsTrial-Installer.exe`
- **Size:** ~20 MB (compressed)
- **Pros:** Professional, smaller download, registry entries
- **Cons:** Requires installation
- **Best for:** Public releases, regular users

### Option C: Portable Installer
- Keep both executable and installer
- Users can run standalone or install

## Code Signing

### Why Sign Your Code?
- Prevents "Unknown Publisher" warning
- Builds user trust
- Required for certain distribution channels

### How to Sign (Windows)

1. **Obtain a Code Signing Certificate:**
   - Self-signed (free, shows as "Unknown Publisher"): 
     ```powershell
     New-SelfSignedCertificate -CertStoreLocation cert:\LocalMachine\My -Subject "CN=KingsTrial" -Type CodeSigningCert
     ```
   - Professional certificate (paid, ~$200-400/year):
     - Sectigo, DigiCert, GlobalSign, etc.

2. **Sign the Executable:**
   ```powershell
   Set-AuthenticodeSignature -FilePath .\KingsTrial.exe `
     -Certificate (Get-ChildItem Cert:\LocalMachine\My | Where-Object {$_.Subject -match "KingsTrial"}) `
     -TimestampServer "http://timestamp.sectigo.com"
   ```

3. **Verify Signature:**
   ```powershell
   Get-AuthenticodeSignature .\KingsTrial.exe | Format-List
   ```

## Build System Configuration

### Modified Build Script Settings

The `build.ps1` and `build.bat` scripts:
- Clean previous builds before compiling
- Include all necessary assets (assets folder, config.json)
- Hidden imports: scenes, ai, ui (custom modules)
- Windowed mode (no console)
- Single-file output

### Customizing Builds

Edit `build.ps1` or `build.bat` to:
- Change executable name (--name parameter)
- Add/remove hidden imports (--hidden-import)
- Include additional data files (--add-data)
- Change output location (OutFile in installer.nsi)

## Troubleshooting

### Issue: "Unknown Publisher" Warning
**Solution:** Sign the executable (see Code Signing section)

### Issue: Missing DLLs
**Solution:** Already handled by PyInstaller with current build configuration

### Issue: Large File Size
**Pros:** Standalone, no dependencies needed
**Options:** 
- Use 7-Zip compression for distribution
- Consider UPX compression (add to PyInstaller)

### Issue: Slow Startup
**Normal:** ~5-10 seconds on first launch (extracting dependencies)
**Future launches:** Faster due to caching

## Release Checklist

- [ ] Run `build.ps1` to create executable
- [ ] Test `dist/KingsTrial.exe` on clean Windows system
- [ ] Create installer via NSIS
- [ ] Test installer on clean Windows system
- [ ] Sign executable(s) if releasing publicly
- [ ] Create release notes documenting:
  - Version number
  - Bug fixes
  - New features
  - Known issues
- [ ] Upload to distribution platform (GitHub, itch.io, Steam, etc.)

## Distribution Platforms

Popular options for distributing indie games:
- **GitHub Releases:** Free, good for open-source
- **itch.io:** Free/paid, designed for games
- **Steam:** $100 deposit, largest platform
- **Your own website:** Full control, requires hosting
- **GameJolt:** Free hosting for indie games

## Additional Resources

- PyInstaller Docs: https://pyinstaller.org/
- NSIS Documentation: https://nsis.sourceforge.io/Docs/
- Windows Code Signing: https://docs.microsoft.com/en-us/windows/win32/seccrypto/introduction-to-code-signing
- Inno Setup: https://jrsoftware.org/isinfo.php
