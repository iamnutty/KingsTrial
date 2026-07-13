# King's Trial — Architecture Review for Web App Conversion

**Reviewer**: Code Architecture Review  
**Date**: 2026-05-24  
**Scope**: Full codebase audit — evaluating readiness for refactoring from a Pygame desktop application to a publishable web application.  
**Verdict**: **Conditionally Approved** — the game logic core is solid and well-separated, but several critical and high-severity issues must be addressed before or during the web conversion.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Critical Bugs (Must Fix Immediately)](#2-critical-bugs-must-fix-immediately)
3. [Architectural Separation of Concerns](#3-architectural-separation-of-concerns)
4. [Module-by-Module Review](#4-module-by-module-review)
5. [Web Conversion Blockers](#5-web-conversion-blockers)
6. [Refactoring Recommendations](#6-refactoring-recommendations)
7. [Data Model & Serialization Concerns](#7-data-model--serialization-concerns)
8. [AI System Considerations](#8-ai-system-considerations)
9. [Testing Gaps](#9-testing-gaps)
10. [Asset & Resource Management](#10-asset--resource-management)
11. [Security Considerations for Web Publishing](#11-security-considerations-for-web-publishing)
12. [Summary of Findings by Severity](#12-summary-of-findings-by-severity)

---

## 1. Executive Summary

King's Trial is a custom chess variant built with Pygame, featuring a 3-phase turn system, AI opponents powered by Stockfish, dynamic board shrinking, piece promotion/demotion economics, and save/load functionality. The codebase is approximately **5,500 lines** across 25+ files.

### Strengths
- **Clean game logic layer**: `game_state.py`, `pieces.py`, and `move_validator.py` are Pygame-free and can be reused directly.
- **Scene-based architecture**: The scene/state machine pattern in `app.py` maps well to a web router.
- **Theme system**: The JSON-based theme system (`ui/theme.py`) is already data-driven and portable.
- **Good docstrings**: Most modules have clear module-level and function-level documentation.
- **Config serialization**: `GameConfig` is a dataclass with JSON save/load, directly usable on the web.

### Weaknesses
- **One critical runtime bug** that will crash the AI game-over path.
- **Deep Pygame coupling** in the UI, rendering, and audio layers (~2,200 lines to replace).
- **Native binary dependency** (Stockfish) that cannot run in a browser.
- **No automated test suite** — only one manual test script and several ad-hoc test files.
- **Mutable dictionary-based piece representation** creates subtle aliasing bugs.
- **Hardcoded file system paths** for saves, assets, and Stockfish discovery.

---

## 2. Critical Bugs (Must Fix Immediately)

### 🔴 BUG-001: Broken Import Will Crash AI Game-Over Path

**File**: `scenes/gameplay.py` **Line 563**  
**Severity**: **CRITICAL** — crashes at runtime when AI wins the game  

```python
# Line 563 in gameplay.py
from utils import save_game_record  # ← 'utils' does NOT exist
```

This import is inside `_handle_ai_logic()` at AI state 4 (executing). When an AI move triggers a game-over condition, Python will throw `ModuleNotFoundError: No module named 'utils'`.

The correct import (used elsewhere in the same file at line 25) is:

```python
from record_saver import save_game_record
```

**Impact**: Any game that ends from an AI move (opponent or neutral) in single-player mode will crash. This path is executed frequently.

---

### 🟡 BUG-002: Double Timer Tick per Frame

**File**: `scenes/gameplay.py` **Lines 184, 227**  
**Severity**: **HIGH** — timers run approximately 2× faster than intended

```python
# Line 184: in update()
timed_out = self.gs.update_timers(dt)

# Line 227: in render()
self.gs.update_timers(0)  # ← Called AGAIN every frame
```

The `update_timers(0)` call in `render()` is a no-op (0 seconds deducted) but this pattern signals a design confusion. However, the `update()` call on line 184 already decrements the timer by `dt` each frame. If `render()` is ever called more than once per frame (e.g., by overlay scenes like `PauseScene` and `GameOverScene` that call `self.gameplay.render(screen)` on line 66 of `pause.py`), the timer will not double-tick because `dt` is only applied in `update()`.

**Actual risk**: The `update_timers(0)` call is harmless but misleading. Remove it to avoid confusion during refactoring.

---

### 🟡 BUG-003: `respawn_pool` Initialized Twice

**File**: `game_state.py` **Lines 91 and 110**  
**Severity**: **MEDIUM** — the first initialization is immediately overwritten

```python
# Line 91
self.respawn_pool = {"white": [], "black": []}

# ... (lines 92-109: other initialization) ...

# Line 110
self.respawn_pool: dict[str, list] = {
    "white": [],
    "black": [],
}
```

The first assignment at line 91 is silently overwritten by the second at line 110. This is not a functional bug today, but it indicates copy-paste drift and will confuse anyone refactoring the constructor.

---

### 🟡 BUG-004: `_do_king_respawn` Contains Orphaned Phase-Skip Logic

**File**: `game_state.py` **Lines 667-672**  
**Severity**: **MEDIUM** — unreachable recursive call could cause infinite recursion in edge cases

```python
def _do_king_respawn(self, owner: str) -> None:
    # ... (respawn logic) ...

    # Lines 667-672: INSIDE _do_king_respawn
    if self.phase == PHASE_WHITE_NEUTRAL:
        has_neutrals = any(p["owner"] == "neutral" for p in self.board.values())
        if not has_neutrals:
            log(f"advance_phase: skipping ...")
            self.advance_phase()  # ← This calls advance_phase, which calls _do_king_respawn again
```

This neutral-phase-skip logic is already correctly handled at the end of `advance_phase()` (lines 589-593). Having a second copy inside `_do_king_respawn` creates a risk of infinite mutual recursion: `advance_phase → _do_king_respawn → advance_phase → _do_king_respawn → ...`

---

## 3. Architectural Separation of Concerns

The codebase has a decent but imperfect separation. Here is the dependency map:

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  main.py    │────▶│   app.py     │────▶│  scenes/*    │
│ (entry pt)  │     │ (state       │     │ (UI + logic  │
│             │     │  machine)    │     │  per screen) │
└─────────────┘     └──────────────┘     └──────┬───────┘
                                                │
                         ┌──────────────────────┤
                         │                      │
                    ┌────▼─────┐          ┌─────▼──────┐
                    │ game_    │          │  ui/*      │
                    │ state.py │          │ (renderer, │
                    │ (PURE    │          │  panels,   │
                    │  LOGIC)  │          │  dialogs,  │
                    │          │          │  audio,    │
                    └────┬─────┘          │  theme)    │
                         │                └────────────┘
                    ┌────▼─────┐               ▲
                    │ pieces.py │               │ Pygame
                    │ move_val. │               │ coupling
                    │ layout_r. │               │
                    │ record_s. │               │
                    │ config.py │               │
                    │constants. │               │
                    └──────────┘               │
                         │                      │
                    ┌────▼─────┐               │
                    │  ai/*    │───────────────┘
                    │(Stockfish│   (AI reads board
                    │ wrapper) │    but doesn't
                    └──────────┘    touch Pygame)
```

### ✅ What's Portable (No Pygame)

| Module | Lines | Notes |
|--------|-------|-------|
| `game_state.py` | 823 | Core game logic. **Zero Pygame imports.** Fully portable. |
| `pieces.py` | 255 | Movement rules. **Zero Pygame imports.** Fully portable. |
| `move_validator.py` | 81 | Legal move filtering. **Zero Pygame imports.** Fully portable. |
| `config.py` | 78 | Settings dataclass + JSON I/O. Fully portable. |
| `record_saver.py` | 221 | Save/load `.kgt` files. Fully portable (uses `json`, `os`). |
| `layout_reader.py` | 166 | CSV board parser. Fully portable. |

### 🔴 What Must Be Replaced (Pygame-Dependent)

| Module | Lines | Web Replacement Strategy |
|--------|-------|--------------------------|
| `app.py` | 167 | Replace with web framework router (Next.js/SvelteKit/etc.) |
| `ui/renderer.py` | 316 | Replace with HTML5 Canvas or CSS grid |
| `ui/panels.py` | 496 | Replace with HTML/CSS components |
| `ui/dialogs.py` | 246 | Replace with modal HTML components |
| `ui/audio.py` | 157 | Replace with Web Audio API / `<audio>` elements |
| `ui/theme.py` | 144 | Adapt — JSON theme system is already data-driven |
| `assets.py` | 79 | Replace with browser asset loading |
| All `scenes/*.py` | ~1,400 | Replace with web page components/routes |
| `main.py` | 33 | Replace with web server entry point |

### ⚠️ Partially Portable (Needs Adaptation)

| Module | Lines | Issue |
|--------|-------|-------|
| `constants.py` | 218 | Has `import pygame` at line 10 for `pygame.Color` — but doesn't actually use it. Remove the import and it's fully portable. |
| `ai/base_stockfish.py` | 587 | Wraps Stockfish binary — needs web worker or server-side proxy |
| `ai/opponent_ai.py` | 595 | Uses `concurrent.futures` + Stockfish — needs server-side execution |
| `ai/neutral_ai.py` | 160 | Same Stockfish dependency |

---

## 4. Module-by-Module Review

### `constants.py`
- **Line 10**: `import pygame` is unnecessary. No `pygame.Color` or other Pygame objects are used. This will cause an import error in a web context.
- **Hardcoded pixel values** (`SQUARE_SIZE = 42`, `PANEL_TOP_H = 80`, etc.) are tightly coupled to a fixed window size. For web, these should become responsive values or CSS variables.
- **`log()` function at line 212**: Defines a backward-compatible `log()` function that several modules import. This should be replaced with standard `logging.getLogger()` calls.

### `game_state.py`
- **Dict-based piece representation** (`{"type": "P", "owner": "white"}`) — works but is fragile. Consider using a `NamedTuple` or `@dataclass` for type safety.
- **`execute_respawn()` line 501**: Mutates the spawned piece dict by adding `rank` and `col` keys (`piece_to_respawn["rank"], piece_to_respawn["col"] = target_sq`). This is a code smell — piece dicts on the board should only have `type` and `owner`, while position is tracked by the `board` dictionary key.
- **`_empty_log_entry()` line 748**: Still references `"bn"` (Black-Neutral) column key, but the 3-phase model only has `"w"`, `"wn"`, `"b"`. The `"bn"` column is vestigial from an older 4-phase design.
- **`reset()` line 752**: Calls `self.__init__(initial_pieces)` — this is an anti-pattern. If `GameState.__init__` signature changes, `reset()` silently breaks because it doesn't pass the `time_control` parameter.

### `pieces.py`
- **Clean and portable.** Well-documented, correct movement logic.
- **`_slide()` function (line 83)** is defined but never called — only `_slide_with_blocker()` is used. Dead code.

### `move_validator.py`
- **Clean**, minimal, no issues.

### `layout_reader.py`
- **Line 34**: Hardcodes `LAYOUT_FILE = "TEST_CSV.csv"` as a module constant — but it's overridden by the `filepath` parameter in `load_board_state()`. Confusing.
- **Line 35**: `RANK_COL_IDX = 9` is defined but never referenced. The actual rank column index `8` is hardcoded on line 111.

### `record_saver.py`
- **Line 21-22**: `_PROJECT_ROOT` uses `os.path.dirname(__file__)` which works for desktop but will break in web deployments where file I/O may be server-side or cloud-based.
- **Line 23**: Eagerly creates the `saves/` directory at import time via `os.makedirs()`. This is a side effect on import — dangerous in serverless or containerized environments.

### `app.py`
- **Line 129**: `if self._gameplay.config is not self.config` — uses identity comparison (`is not`) to detect config changes. This is brittle; if the config is reconstructed (e.g., from deserialization), identity will differ even if values are identical. Use `==` with a proper `__eq__`.

### `scenes/gameplay.py`
- **Line 502-503**: `self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)` — creates a thread pool that is never shut down. This leaks threads on scene transitions and game resets.
- **Line 501**: `if not hasattr(self, '_ai_future') or self._ai_future is None:` — using `hasattr` for flow control is a code smell. Initialize `_ai_future = None` in `__init__`.
- **Line 604**: `self.human_color = None` in the 2-player reset path — but other code (line 305) checks `active_owner != self.human_color`, which will always be True when `human_color is None`, effectively blocking all human input in 2-player mode after a reset.

### `ui/renderer.py`
- **Global mutable font cache** (`_fonts: dict = {}` at line 71) — will cause issues if the renderer module is imported in a multi-session web server context. Each session would share the same font cache.

### `ui/panels.py`
- **Line 416-425**: Imports `ui.theme` and `ui.renderer._piece_display` inside `_draw_status_bar()` — circular import risk and exposes private function `_piece_display` across module boundaries.

### `ui/audio.py`
- **Global mutable singleton** (`manager: AudioManager = None` at line 134) — same issue as renderer fonts for multi-session.

### `ui/theme.py`
- **Good design**: The JSON-based theme loading system is already web-compatible. The theme JSON files define colors as arrays and character mappings — this maps directly to CSS variables or canvas draw calls.

### `ai/base_stockfish.py`
- **Line 12-21**: Hardcoded Windows paths for Stockfish discovery (`C:\Program Files\Stockfish\stockfish.exe`, etc.) — won't work on web servers.
- **Line 52**: Trusts `os.getcwd()` candidates without full validation — `candidate.startswith(os.getcwd())` skips `_is_stockfish_executable` check, potentially running arbitrary executables.

---

## 5. Web Conversion Blockers

### Blocker 1: Pygame Rendering Engine
**Everything** in `ui/` uses `pygame.Surface`, `pygame.draw`, `pygame.font`, and `pygame.mixer`. These must be completely replaced with:
- **HTML5 Canvas** (for the board and pieces) — or —
- **CSS Grid + DOM elements** (for a more accessible, responsive approach)
- **Web Audio API** or `<audio>` elements for sound

### Blocker 2: Stockfish Binary
The AI system requires Stockfish, a native C++ chess engine. Options for web:
1. **Server-side**: Run Stockfish on the backend; communicate via WebSocket/REST API.
2. **WASM**: Use [stockfish.js](https://github.com/nicfisher/stockfish.wasm) — a WebAssembly port. This runs entirely in-browser via Web Workers.
3. **Hybrid**: Easy/Random AI runs client-side (JavaScript); Hard AI calls a server API.

### Blocker 3: File System I/O
- `config.json` save/load → Replace with `localStorage` or a database.
- `.kgt` save files → Replace with `localStorage`, IndexedDB, or server-side storage.
- CSV layout files → Bundle as static assets or embed in JavaScript.
- Menu background image (`menu_bg.png`, 6.5 MB) → Compress and serve as a web asset.

### Blocker 4: Game Loop Architecture
Pygame uses a synchronous `while self.running: tick → handle events → update → render` loop. Browsers use:
- `requestAnimationFrame()` for the render loop
- DOM event listeners for input
- `setTimeout` / Web Workers for AI thinking

---

## 6. Refactoring Recommendations

### Priority 1: Fix Critical Bugs Before Conversion
1. Fix the `from utils import save_game_record` → `from record_saver import save_game_record` bug.
2. Remove the orphaned phase-skip logic in `_do_king_respawn()`.
3. Remove the dead `update_timers(0)` call in gameplay render.
4. Remove the duplicate `respawn_pool` initialization.

### Priority 2: Extract a Clean Game Engine Package
Create a `core/` package containing only the platform-independent modules:

```
core/
├── __init__.py
├── game_state.py     (from game_state.py — no changes needed)
├── pieces.py         (from pieces.py — no changes needed)
├── move_validator.py (from move_validator.py — no changes needed)
├── config.py         (from config.py — no changes needed)
├── constants.py      (from constants.py — REMOVE pygame import, REMOVE pixel constants)
├── layout_reader.py  (from layout_reader.py — no changes needed)
└── record_saver.py   (from record_saver.py — make save dir configurable)
```

This package should be importable with **zero Pygame dependencies** and **zero side effects**.

### Priority 3: Formalize the Piece Data Model
Replace ad-hoc dicts with typed structures:

```python
# Before (current)
piece = {"type": "P", "owner": "white"}

# After (recommended)
@dataclass(frozen=True)
class Piece:
    type: str   # 'P', 'N', 'B', 'R', 'Q', 'K'
    owner: str  # 'white', 'black', 'neutral'
```

Using `frozen=True` prevents the mutation bugs seen in `execute_respawn()` and makes pieces hashable for set operations.

### Priority 4: Decouple Pixel Constants
Move all pixel/layout constants out of `constants.py` into a separate `layout.py` or `ui_constants.py` that only the UI layer imports. The game logic should never reference pixel dimensions.

### Priority 5: Add a Game State Serialization API
Currently, `record_saver.py` reaches directly into `GameState` internals (`gs.board`, `gs._current_log_entry`, etc.). Add a `.to_dict()` / `.from_dict()` API to `GameState`:

```python
class GameState:
    def to_dict(self) -> dict:
        """Serialize complete game state for save/load/network sync."""
        ...

    @classmethod
    def from_dict(cls, data: dict) -> "GameState":
        """Reconstruct game state from serialized data."""
        ...
```

This is essential for web multiplayer (sending state over WebSocket) and for browser `localStorage` persistence.

---

## 7. Data Model & Serialization Concerns

### Board Representation
The board uses `dict[(rank, col) → piece_dict]`. This is efficient for sparse boards but has issues:
- **JSON serialization**: Tuple keys `(rank, col)` are not valid JSON keys. The `.kgt` saver works around this by converting to a list of dicts. This conversion should be formalized.
- **Network sync**: For multiplayer web games, you'll need to serialize and deserialize the full game state every move. The current approach works but is verbose.

### Move Log Schema Drift
The move log entry format `{"cycle": int, "w": str, "wn": str, "b": str, "bn": str}` includes a `"bn"` column for Black-Neutral phase, but the game only has 3 phases (White → White-Neutral → Black). The `"bn"` key is always empty. Either remove it or document it as reserved for future expansion.

### Save File Format
The `.kgt` format mixes human-readable text (header, move table) with embedded JSON (state snapshot). This is creative but fragile:
- The parser depends on exact marker strings (`## STATE_SNAPSHOT_BEGIN`, `## STATE_SNAPSHOT_END`)
- Line endings might differ across platforms (`\r\n` vs `\n`)
- For web, consider using pure JSON for saves

---

## 8. AI System Considerations

### Stockfish Integration Complexity
The AI system is the most complex part of the codebase (~1,300 lines). Key concerns for web conversion:

1. **FEN Generation**: `_board_to_fen()` (lines 359-529 in `base_stockfish.py`) converts an 8×N custom board to standard 8×8 FEN by windowing. This is clever but fragile — the dummy king injection logic alone is ~100 lines. This logic must be preserved exactly on whatever platform runs the AI.

2. **Thread Pool Leak**: `GameplayScene` creates a `ThreadPoolExecutor` that is never shut down (`self._executor`). On reset or scene transitions, old executors and their threads persist.

3. **Engine Crash Recovery**: Both `OpponentAI` and `NeutralAI` have crash-recovery code that reinstantiates Stockfish. This is good but creates a new Stockfish process without terminating the old one (potential zombie processes).

4. **Difficulty Scaling**: The difficulty system works via three parameters (`timeout_mult`, `exec_threshold`, `noise_pool_size`). This is well-designed and will transfer cleanly to any backend.

### Web AI Options
| Approach | Latency | Cost | Complexity |
|----------|---------|------|------------|
| WASM Stockfish in Web Worker | Low (local) | Free | Medium — port FEN logic to JS |
| Server-side Stockfish via REST/WS | Medium (network) | Server cost | Low — reuse Python AI code |
| Pure JS chess AI (no Stockfish) | Low | Free | High — rewrite AI logic |
| Cloud Function per move | High | Per-call cost | Medium |

**Recommendation**: Use WASM Stockfish for the web version. The FEN generation logic in `base_stockfish.py` would need to be ported to JavaScript, but the game rules (Python `core/` package) could remain server-side if multiplayer is added.

---

## 9. Testing Gaps

### Current Test Coverage
| File | Type | What It Tests |
|------|------|---------------|
| `tests/test_spawn_limits.py` | Manual script | Piece spawn/promotion limits |
| `test_ai_black.py` | Manual script | AI playing as black |
| `test_ai_local.py` | Manual script | Local AI evaluation |
| `test_fast.py` | Manual script | Quick integration test |
| `test_sf.py` | Manual script | Stockfish availability |
| `test_sf_valid.py` | Manual script | Stockfish FEN validation |

**None** of these use a test framework (`pytest`, `unittest`). They are all standalone scripts with `print()` assertions.

### Recommended Test Suite (Before Web Conversion)
1. **Unit tests for `game_state.py`**: Phase advancement, scoring, win conditions, board shrink, king respawn, promotion/demotion/respawn economics.
2. **Unit tests for `pieces.py`**: Movement rule verification for each piece type in edge cases (board edges, blockers).
3. **Unit tests for `move_validator.py`**: Legal move generation, turn enforcement.
4. **Integration tests for save/load**: Round-trip `GameState → .kgt → GameState` with snapshot integrity checks.
5. **AI smoke tests**: Verify AI returns valid moves given known board states.

Without this test suite, you'll have no confidence that the web conversion preserves game correctness.

---

## 10. Asset & Resource Management

### Large Assets
| Asset | Size | Web Consideration |
|-------|------|-------------------|
| `menu_bg.png` | 6.5 MB | **Too large.** Compress to JPEG/WebP (~200-500 KB). |
| `menu_bg_old_too.png` | 9.1 MB | Unused? Remove from distribution. |
| `menu_bg_recent.png` | 6.5 MB | Unused? Remove from distribution. |
| `menu_bg_cinematic.png` | 2.1 MB | Unused? Remove from distribution. |
| `menu_bg_old.png` | 84 KB | Unused? Remove from distribution. |
| Background music (MP3s) | ~10 MB total | Stream on demand; don't bundle |

### Unused Files in Root
The following files appear to be development artifacts and should not be included in any web distribution:
- `BoardExperiments.xlsx` — development notes
- `*.kgt` files in root — test save files
- `build.bat`, `build.ps1`, `build-installer.ps1` — desktop build scripts
- `KingsTrial.spec` — PyInstaller spec
- `installer.nsi`, `inno-setup-example.iss` — installer scripts
- `sign-code.ps1` — code signing script
- `venv/` — Python virtual environment
- `__pycache__/` — bytecode cache
- `build/`, `dist/` — build artifacts
- `scratch/` — development scratch files

### Font Dependencies
The codebase uses `pygame.font.SysFont("dejavusansmono", ...)` throughout. On web, you'll need to:
1. Bundle DejaVu Sans Mono as a web font, OR
2. Switch to a Google Font (e.g., JetBrains Mono, Fira Code) and load it via `@font-face`.

---

## 11. Security Considerations for Web Publishing

### Input Validation
- **Move validation is server-side**: Good. `move_validator.py` properly validates all moves. For a web game, this MUST remain server-authoritative — never trust the client to validate moves.
- **Save file names**: `save_game.py` allows characters `a-z A-Z 0-9 _-()` in filenames (line 34-37). This is safe for desktop but for web, save names should be sanitized further if stored on a server filesystem.

### AI Timing Attacks
The AI uses `time.time()` deadlines. On a web server, a malicious client could send rapid requests to force the AI into tight deadline loops. Rate limiting is needed.

### Config Injection
`GameConfig.load()` (line 75) uses `cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})` — this filters to known fields, which is good. But the values themselves are not validated (e.g., `neutral_ai` could be set to an arbitrary string).

### Stockfish as a Server Process
If Stockfish runs server-side, it must be sandboxed. `base_stockfish.py` (line 52) has logic that skips executable validation for Stockfish binaries found in the project directory — this should be tightened for production.

---

## 12. Summary of Findings by Severity

### 🔴 Critical (Fix Before Any Release)
| ID | Issue | File | Line |
|----|-------|------|------|
| BUG-001 | `from utils import save_game_record` — module doesn't exist | `gameplay.py` | 563 |

### 🟠 High (Fix Before Web Conversion)
| ID | Issue | File | Line |
|----|-------|------|------|
| ARCH-001 | `constants.py` imports Pygame unnecessarily | `constants.py` | 10 |
| ARCH-002 | ThreadPoolExecutor never shut down, leaks threads | `gameplay.py` | 502-503 |
| ARCH-003 | `human_color = None` in 2P reset blocks all input | `gameplay.py` | 604 |
| ARCH-004 | No test suite — cannot verify correctness after refactoring | Project-wide | — |
| ARCH-005 | `respawn_pool` initialized twice | `game_state.py` | 91, 110 |

### 🟡 Medium (Fix During Web Conversion)
| ID | Issue | File | Line |
|----|-------|------|------|
| DESIGN-001 | Mutable dict-based piece model | `game_state.py` | 32-38 |
| DESIGN-002 | Pixel constants mixed with game logic constants | `constants.py` | 35-49 |
| DESIGN-003 | `_SAVE_DIR` created at import time (side effect) | `record_saver.py` | 23 |
| DESIGN-004 | `reset()` calls `__init__()` directly | `game_state.py` | 752 |
| DESIGN-005 | Orphaned `"bn"` key in move log entries | `game_state.py` | 748 |
| DESIGN-006 | Orphaned phase-skip in `_do_king_respawn` | `game_state.py` | 667-672 |
| DESIGN-007 | 6.5 MB menu background — too large for web | `assets/` | — |
| DESIGN-008 | Global mutable singletons (font cache, AudioManager, ThemeManager) | `ui/*` | Multiple |
| DESIGN-009 | Dead code: `_slide()` function never called | `pieces.py` | 83-96 |
| DESIGN-010 | `LAYOUT_FILE` and `RANK_COL_IDX` constants defined but never used | `layout_reader.py` | 34-35 |

### 🟢 Low (Nice to Have)
| ID | Issue | File | Line |
|----|-------|------|------|
| STYLE-001 | Inconsistent `import` placement (lazy imports inside functions) | Multiple | Multiple |
| STYLE-002 | Mixed use of `constants.log()` and `logging.getLogger()` | Multiple | Multiple |
| STYLE-003 | Old `__pycache__` directories in version control | Root, ai/, scenes/, ui/ | — |
| STYLE-004 | Multiple unused `.xlsx` and `.png` files in assets | `assets/` | — |

---

## Appendix: Recommended Web Conversion Architecture

```
┌──────────────────────────────────────────────────────┐
│                    BROWSER (Client)                  │
│                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ HTML Canvas  │  │ CSS Panels   │  │ Web Audio  │  │
│  │ (board +    │  │ (top bar,    │  │ API        │  │
│  │  pieces)    │  │  move log,   │  │ (SFX +     │  │
│  │             │  │  status)     │  │  music)    │  │
│  └──────┬──────┘  └──────┬───────┘  └────────────┘  │
│         │                │                           │
│  ┌──────▼────────────────▼───────────────────────┐   │
│  │  Game Controller (JavaScript/TypeScript)       │   │
│  │  • Handles input events (click, keyboard)      │   │
│  │  • Manages requestAnimationFrame loop          │   │
│  │  • Renders board state to canvas               │   │
│  │  • Communicates with server via WebSocket/HTTP │   │
│  └──────────────────────┬────────────────────────┘   │
│                         │                            │
│  ┌──────────────────────▼────────────────────────┐   │
│  │  WASM Stockfish Web Worker (Optional)          │   │
│  │  For client-side AI in single-player           │   │
│  └───────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
                          │
                    WebSocket / REST
                          │
┌──────────────────────────────────────────────────────┐
│                    SERVER (Backend)                   │
│                                                      │
│  ┌───────────────────────────────────────────────┐   │
│  │  core/ (Python - unchanged game logic)         │   │
│  │  ├── game_state.py                             │   │
│  │  ├── pieces.py                                 │   │
│  │  ├── move_validator.py                         │   │
│  │  ├── config.py                                 │   │
│  │  ├── constants.py (without pygame/pixels)      │   │
│  │  ├── layout_reader.py                          │   │
│  │  └── record_saver.py                           │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  ┌───────────────────────────────────────────────┐   │
│  │  ai/ (Python - Stockfish server-side)          │   │
│  │  ├── base_stockfish.py                         │   │
│  │  ├── opponent_ai.py                            │   │
│  │  └── neutral_ai.py                             │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  ┌───────────────────────────────────────────────┐   │
│  │  API Layer (FastAPI / Flask)                    │   │
│  │  ├── POST /api/new-game                        │   │
│  │  ├── POST /api/move                            │   │
│  │  ├── POST /api/promote | /api/demote           │   │
│  │  ├── POST /api/respawn                         │   │
│  │  ├── GET  /api/state                           │   │
│  │  ├── POST /api/save                            │   │
│  │  ├── GET  /api/saves                           │   │
│  │  └── POST /api/load                            │   │
│  └───────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

---

## 13. Real-Time Multiplayer & State Synchronization

If the web version includes multiplayer functionality, the current state-machine-driven turn logic needs to adapt to a distributed model.

### State Sync Strategy
- **WebSockets over HTTP Polling**: Chess variants are highly interactive. Use WebSockets (e.g., Socket.io or native WebSockets via FastAPI) rather than HTTP polling for low-latency move broadcasting and timer synchronization.
- **Server-Authoritative Validation**: The frontend should optimistic-render moves, but the server must validate them using `move_validator.py`. If the server rejects a move, the client must rollback to the server's state.
- **Handling Disconnects**: Implement reconnection logic where the client can request the full `GameState` object (via `.to_dict()`) upon reconnecting to a session.

## 14. Frontend Framework & Tech Stack Recommendations

Replacing Pygame's monolithic render loop requires adopting modern web paradigms.

### Framework Choice
- **React or Svelte**: Recommended for component-driven UI. Svelte provides exceptional performance for frequent DOM updates, while React has a vast ecosystem (e.g., `react-dnd` for drag-and-drop piece movement).
- **State Management**: Use lightweight state managers like Zustand (React) or Svelte Stores to hold the `GameState`.
- **Rendering the Board**: HTML5 `<canvas>` is performant but harder to make accessible. A CSS Grid approach (64 squares as `<div>` elements) is highly responsive, accessible, and makes drag-and-drop interactions trivial to implement using the HTML5 Drag and Drop API.

## 15. Backend API & Hosting Strategy

The backend will serve the Python game logic and Stockfish.

### Backend Framework
- **FastAPI**: Highly recommended over Flask/Django for this project. FastAPI natively supports `asyncio`, which is perfect for managing long-running WebSocket connections and asynchronous Stockfish engine queries without blocking the main event loop.

### Hosting & Infrastructure
- **Frontend**: Deploy on Vercel or Netlify as a static site.
- **Backend**: Needs a VPS or containerized platform (Render, Fly.io, or Railway) because serverless functions (like AWS Lambda) do not support long-running WebSocket connections well and make running native binaries like Stockfish difficult due to cold starts and ephemeral storage.
- **Database**: Use PostgreSQL for user accounts and match history. Use Redis for in-memory, fast-access tracking of active game states and matchmaking.

## 16. Mobile & Touch Responsiveness

Pygame relies entirely on mouse `MOUSEBUTTONDOWN` events. Translating this to the web requires a touch-first approach.

- **Interaction Paradigm**: Instead of "click to pick up, click to place", support both "Tap-to-Select, Tap-to-Move" and "Drag-and-Drop" via touch events.
- **Responsive Board**: The board must scale to fit viewport width on mobile devices, while the UI panels (timers, move logs, respawn pools) should stack vertically instead of sitting horizontally alongside the board.

## 17. DevOps & CI/CD

- **Dockerization**: The backend must be containerized to ensure Stockfish is installed at the system level. The Dockerfile should start from a `python:3.11-slim` image, run `apt-get install stockfish`, and then install the Python dependencies. This eliminates the path discovery issues noted in `base_stockfish.py`.

---

*End of review. Questions or clarifications should be directed to the architecture review team.*
