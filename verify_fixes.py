"""
verify_fixes.py
Smoke test to confirm all bug-fix changes are working correctly.
Run from c:\\Projects\\KingsTrial: python verify_fixes.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

PASS = []
FAIL = []

def check(name, result, note=""):
    if result:
        PASS.append(name)
        print(f"  [PASS] {name}" + (f" — {note}" if note else ""))
    else:
        FAIL.append(name)
        print(f"  [FAIL] {name}" + (f" — {note}" if note else ""))

print("=== Core module imports ===")
try:
    import constants
    check("constants import", True)
except Exception as e:
    check("constants import", False, str(e))

try:
    from config import GameConfig
    check("config import", True)
except Exception as e:
    check("config import", False, str(e))

try:
    from game_state import GameState, make_piece
    check("game_state import", True)
except Exception as e:
    check("game_state import", False, str(e))

try:
    from move_validator import get_legal_moves, get_all_legal_moves
    check("move_validator import", True)
except Exception as e:
    check("move_validator import", False, str(e))

# BUG-015: saves/ must NOT be created at import time
saves_before = os.path.exists(os.path.join(os.path.dirname(__file__), "saves"))
try:
    from record_saver import save_game_record
    saves_after_import = os.path.exists(os.path.join(os.path.dirname(__file__), "saves"))
    created_at_import = (not saves_before) and saves_after_import
    check("BUG-015 record_saver import (no mkdir)", not created_at_import,
          "saves/ created at import — FAIL" if created_at_import else "saves/ not created at import")
except Exception as e:
    check("record_saver import", False, str(e))

print()
print("=== GameState functional checks ===")
try:
    pieces = [
        {"rank": 4,  "col": 5, "type": "K", "owner": "white"},
        {"rank": 23, "col": 4, "type": "K", "owner": "black"},
        {"rank": 5,  "col": 5, "type": "P", "owner": "white"},
    ]
    gs = GameState(pieces, time_control="3+5")
    check("GameState init", True, f"{len(gs.board)} pieces, white timer={gs.timers['white']}s")
except Exception as e:
    check("GameState init", False, str(e))

try:
    # BUG-003: respawn_pool must exist and have correct keys
    check("BUG-003 respawn_pool init", 
          gs.respawn_pool == {"white": [], "black": []},
          str(gs.respawn_pool))
except Exception as e:
    check("BUG-003 respawn_pool init", False, str(e))

try:
    moves = get_all_legal_moves(gs)
    check("get_all_legal_moves", True, f"{len(moves)} moves for white")
except Exception as e:
    check("get_all_legal_moves", False, str(e))

try:
    gs.advance_phase()
    check("advance_phase", True, f"now: {constants.PHASE_NAMES[gs.phase]}")
except Exception as e:
    check("advance_phase", False, str(e))

try:
    # BUG-008: reset() must accept and forward time_control.
    # TIME_CONTROLS has "10+20" (600s), not "10+5" — use the correct key.
    gs.reset(pieces, time_control="10+20")
    check("BUG-008 GameState.reset time_control",
          gs.timers["white"] == 600.0,
          f"timer={gs.timers['white']}s (expected 600.0 for '10+20')")
except Exception as e:
    check("BUG-008 GameState.reset time_control", False, str(e))

try:
    # BUG-009 / BUG-010: removed dead methods should not exist
    has_old = hasattr(gs, "auto_respawn_king") or hasattr(gs, "perform_ai_move") or hasattr(gs, "get_random_ai_move")
    check("BUG-009/010 dead methods removed", not has_old,
          "dead methods still present" if has_old else "auto_respawn_king / perform_ai_move / get_random_ai_move all removed")
except Exception as e:
    check("BUG-009/010 dead methods removed", False, str(e))

print()
print("=== Config checks ===")
try:
    cfg = GameConfig.load("config.json")
    check("GameConfig.load", True, f"theme={cfg.theme}")
except Exception as e:
    check("GameConfig.load", False, str(e))

try:
    import json, tempfile, os as _os
    bad_cfg = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    bad_cfg.write("{this is not json}")
    bad_cfg.close()
    import logging
    logging.basicConfig(level=logging.WARNING)
    result = GameConfig.load(bad_cfg.name)
    _os.unlink(bad_cfg.name)
    check("BUG-012 malformed config returns defaults", isinstance(result, GameConfig),
          "returned defaults for malformed JSON")
except Exception as e:
    check("BUG-012 malformed config", False, str(e))

print()
print("=== Summary ===")
print(f"  PASSED: {len(PASS)}")
print(f"  FAILED: {len(FAIL)}")
if FAIL:
    print(f"\n  Failed checks: {', '.join(FAIL)}")
    sys.exit(1)
else:
    print("\nAll checks passed!")
