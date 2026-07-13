# Build & Distribution Quick Start

## Files Created

### Build Scripts
- **`build.ps1`** - PowerShell build script (recommended)
- **`build.bat`** - Batch file for Command Prompt
- **`build-installer.ps1`** - Builds NSIS installer
- **`sign-code.ps1`** - Signs executable with certificate

### Installer Configuration
- **`installer.nsi`** - NSIS installer configuration
- **`inno-setup-example.iss`** - Alternative Inno Setup template

### Documentation
- **`DISTRIBUTION.md`** - Complete distribution guide

---

## Quick Start

### 1. Build Executable (One-Time)
```powershell
.\build.ps1
```
✅ Creates: `dist/KingsTrial.exe` (~51 MB)

### 2. Test Executable
```powershell
.\dist\KingsTrial.exe
```

### 3. Create Installer (Optional)

**Install NSIS first:**
- Download: https://nsis.sourceforge.io/Download
- Run installer with default settings

**Then build installer:**
```powershell
.\build-installer.ps1
```
✅ Creates: `KingsTrial-Installer.exe` (~20 MB)

### 4. Sign Code (Optional - For Public Release)
```powershell
# Run as Administrator
.\sign-code.ps1
```
Creates self-signed certificate and signs executable

---

## File Structure After Build

```
KingsTrial/
├── dist/
│   └── KingsTrial.exe          ← Standalone executable
├── KingsTrial-Installer.exe    ← Installer (after step 3)
├── KingsTrial.spec             ← PyInstaller config
└── build/                       ← Build artifacts (can delete)
```

---

## Distribution Options

| Option | Size | Installation | Best For |
|--------|------|--------------|----------|
| **Direct EXE** | 51 MB | None (portable) | Beta, early access |
| **Installer** | 20 MB | InstallDir + Start Menu | Public releases |
| **Compressed ZIP** | <20 MB* | Extract + run | Web download |

*Use 7-Zip for best compression: `7z a KingsTrial.7z dist/KingsTrial.exe`

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Build fails | Run from project root: `cd c:\Projects\KingsTrial` |
| Can't run build.ps1 | Allow execution: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| NSIS not found | Install from: https://nsis.sourceforge.io/Download |
| Installer won't build | Ensure `dist/KingsTrial.exe` exists first |
| "Unknown Publisher" warning | Sign with `sign-code.ps1` (requires admin) |

---

## ⚠️ Windows Console-Window Flash (Stockfish) — Known Issue & Resolution

### Symptom
On Windows (both dev and `.exe` builds), a blank console window flickers open
and immediately closes repeatedly during the Neutral AI or Opponent AI turn.

### Root Cause
The `stockfish` Python library (`models.py`) spawns Stockfish via
`subprocess.Popen` **without** the `CREATE_NO_WINDOW` flag.  This happens in
**two separate places**:

1. `Stockfish.__init__()` — the initial engine start.  
   → Fixed by `_make_stockfish_engine()` in `ai/base_stockfish.py` which
   temporarily monkey-patches `subprocess.Popen` to inject `CREATE_NO_WINDOW`
   before calling the constructor.

2. `Stockfish.is_fen_valid()` — the library creates a **second, entirely new**
   Stockfish subprocess on every call to validate a FEN string.  This happens
   outside our monkey-patch window and fires 2–5 times per AI turn.  
   → Fixed by replacing every `engine.is_fen_valid(fen)` call in the codebase
   with `_is_fen_syntax_valid(fen)` (defined in `ai/base_stockfish.py`), which
   performs the same structural FEN check using only a compiled regex — no
   subprocess is spawned.

### Do Not Reintroduce
- **Never call `engine.is_fen_valid()`** anywhere in the game code.  Always use
  `_is_fen_syntax_valid(fen)` from `ai.base_stockfish`.
- **Never call `Stockfish(...)` directly** outside of `_make_stockfish_engine()`.
  Always go through that helper so the `CREATE_NO_WINDOW` monkey-patch is active.
- If upgrading the `stockfish` Python package, re-inspect `models.py` for new
  calls to `subprocess.Popen` or `subprocess.run` that may reintroduce the issue.

---

## Next Steps

1. ✅ Executable created
2. ✅ Build scripts ready
3. **→ Choose distribution method (see DISTRIBUTION.md)**
4. **→ Sign code for public release (optional)**
5. **→ Create installer (optional)**
6. **→ Upload to distribution platform**

See **DISTRIBUTION.md** for complete guide!
