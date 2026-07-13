# Neutral AI — Decision Logic Reference

## Overview

The `NeutralAI` class (`ai/neutral_ai.py`) drives the **Neutral faction** — the third, autonomous team that plays against both White and Black. It inherits all core infrastructure from `BaseStockfishAI` (`ai/base_stockfish.py`), sharing the Stockfish engine process, FEN builder, square-safety oracle, tactical overrides, and rescue logic.

### Structural differences from OpponentAI

| Aspect | OpponentAI | NeutralAI |
|--------|-----------|-----------|
| **Win condition** | King reaches opposing boundary rank | None — Neutral has no King |
| **Goal** | King advance + point accumulation | Point accumulation only (captures, promotions) |
| **Board coverage** | King-centred single window | Up to 3 parallel windows (North, South, Central) |
| **King Defense step** | Yes (STEP 3) | N/A — no King exists |
| **Spawning** | Adjacent to King (STEP 7) | N/A |
| **Swing formula** | `−after_cp − base_cp` | `after_cp − base_cp` (forward sign) |
| **Engine restart** | `_restart_engine()` method | Inline restart in `choose_move` catch block |

Because Neutral has no King and no winning rank, its entire strategy is about **material domination**: capture high-value enemy pieces, promote Pawns at the board edges, and preserve its own major/minor pieces.

---

## Board Context: The Dual-Board Problem

The playable area spans ranks 4–23 (20 ranks). Stockfish only understands an 8 × 8 FEN. Neutral pieces can exist anywhere on the board simultaneously, including the upper half, lower half, or both. To handle this, `NeutralAI` divides the board into **up to three 8-rank evaluation windows** per turn:

| Window | Covers | Stockfish Active Color | Enemy King Removed |
|--------|--------|------------------------|---------------------|
| **North Board** | Upper half: `mid_rank → PLAYABLE_MAX` | White (`w`) | White King |
| **South Board** | Lower half: `PLAYABLE_MIN → mid_rank` | Black (`b`) | Black King |
| **Central Board** | ±3 ranks around `mid_rank` (hard/insane only) | Both `w` and `b` | Both Kings |

```
mid_rank = (PLAYABLE_MIN + PLAYABLE_MAX) // 2  =  (4 + 23) // 2  =  13
```

**Why different active colors per window?**

The Neutral faction has no inherent "side". The choice of active color controls how Stockfish encodes the Neutral pieces:

- **North Board as White (`w`):** Neutral pieces → uppercase (friendly); White player pieces → lowercase (enemy). Stockfish evaluates from White's perspective, biasing it toward occupying the upper board aggressively.
- **South Board as Black (`b`):** Neutral pieces → lowercase (friendly); Black player pieces → uppercase (enemy). Stockfish evaluates from Black's perspective on the lower board.

**Why strip enemy Kings?**

Player Kings in the same half as their respawn would be treated as enemy Kings in the FEN, triggering illegal-position crashes if a second real King appears alongside the injected dummy. They are removed from the FEN via `remove_kings`, and a Dummy King is safely injected in their place.

---

## Window Selection: `_find_target_board`

```python
_find_target_board(gs, min_r, max_r, scan_down) → (lo, hi) | None
```

For each board half, this method scans all valid 8-rank windows and returns the **most valuable window containing at least one Neutral piece**.

### Scan direction

- **North Board** (`scan_down=True`): Iterates from `max_r` down to `min_r + 7`. Prefers windows closer to the top boundary where Neutral pieces typically cluster.
- **South Board** (`scan_down=False`): Iterates from `min_r` up to `max_r − 7`. Prefers windows closer to the bottom boundary.

### Window scoring (in priority order)

1. **Primary target** — Window has `≥ 2 Neutral pieces` **AND** `≥ 15 combined piece-value points` (counting all pieces, friend and foe, in the window). The **first** such window found in the scan direction is returned immediately without checking further windows.

2. **Best available** — If no window meets criterion 1, the window with the highest total piece value that contains **at least 1 Neutral piece** is tracked and returned after the full scan.

3. **None** — If no Neutral pieces exist anywhere in the half, `None` is returned and that half is **skipped entirely** for this turn. Calling `_evaluate_subboard` on an empty region wastes engine cycles.

### Why `≥ 15 combined value`?

A window with only pawns (value 1 each) has little to gain from Stockfish analysis. The 15-point threshold ensures the engine is only invoked for positions with meaningful material density — a queen (9) + rook (5) = 14 already barely qualifies, incentivising windows with multiple high-value pieces.

---

## Evaluation Currency: Centipawn Swing (NeutralAI variant)

Unlike `OpponentAI`, `NeutralAI` does not invert the sign of the after-state evaluation. It uses **forward swing** computed by `_evaluate_subboard`:

```
swing = after_cp − base_cp
```

| Term | Meaning |
|------|---------|
| `base_cp` | Stockfish eval of the window before any move is made |
| `after_cp` | Centipawn value of the specific top move returned by `get_top_moves(5)` |
| `swing` | Net positional improvement for the AI-as-White (or AI-as-Black) in this window |

A mate detection is mapped to ±10 000 cp:

```python
if move.get("Mate"):
    cp_after = 10000 if move["Mate"] > 0 else -10000
```

### Cross-window accumulation

A key property of `NeutralAI` is that the candidate dictionary **accumulates** swing across all windows:

```python
candidate_moves[(from_sq, to_sq)] += swing
```

If the same move appears in both the North Board's top-5 **and** the South Board's top-5, its score is the **sum of both swings**. This naturally rewards moves that are positionally strong in multiple areas of the board simultaneously — a Neutral piece centralising near `mid_rank` could benefit from both evaluations.

---

## Evaluation Pipeline: 4 Stages

### Stage 0 — Engine Availability Check

```python
if not self.available or self.engine is None:
    return self._get_fallback_move(gs)
```

If Stockfish is not installed, failed to start, or was never initialised (e.g. `difficulty == "random"`), the AI immediately returns a **random legal move** via the base class `_get_fallback_move`. This ensures the game is never frozen regardless of the environment.

---

### Stage 1 — Tactical Overrides (`_check_tactical_overrides`)

This shared method (inherited from `BaseStockfishAI`) runs *before* any engine evaluation. It scans every Neutral piece and its legal moves, applying **hard-coded priority rules** that don't require Stockfish analysis. The highest-priority applicable rule fires immediately and returns.

#### Pre-Override: Danger Cycle Evacuation

At cycles 13–15, 28–30, and 43–45 (within 2 cycles of a board shrink), the outermost two playable ranks on each side are about to be removed. Any Neutral piece sitting on these **danger ranks** (`min_playable_rank`, `min_playable_rank+1`, `max_playable_rank-1`, `max_playable_rank`) will be destroyed when the board shrinks.

Evacuation logic:
1. Collect all Neutral pieces on danger ranks.
2. Sort by **descending piece value** (Queen evacuated before Knight).
3. For each trapped piece, find its first legal move to a safe, non-danger-rank square.
4. Return that evacuation move immediately, before all other priorities.

#### Tactical Priority Table

| Priority | Name | Condition | Difficulty gate |
|----------|------|-----------|-----------------|
| **P0 (pre)** | Evacuation | Neutral piece on a danger rank within 2 cycles of shrink | All |
| **P1** | King Capture (Instakill) | Any Neutral piece can capture an enemy King | All (immediate) |
| **P2** | Queen Capture | Pawn/Knight/Bishop/Rook can take an enemy Queen | ≥ medium |
| **P3** | Safe Pawn Promotion | Neutral Pawn can reach `min_playable_rank` or `max_playable_rank`, and destination is safe | All |
| **P4** | Rook Capture | Pawn/Knight/Bishop can take an enemy Rook | ≥ medium |
| **P5** | Minor Capture (Pawn) | Neutral Pawn can take an enemy Bishop or Knight | ≥ hard |

> **Single winner:** The method iterates all pieces/moves and tracks only the **lowest priority number** found. King Capture (P1) is an immediate return — no further scanning. All others are compared and the best is returned after the full scan.

> **Danger Zone Avoidance:** Even within the tactical override, no piece is moved *into* a danger rank unless the destination is an enemy King capture.

---

### Stage 1.5 — Rescue Override (`_find_rescue_move`)

```python
rescue_move = self._find_rescue_move(gs, ai_owners, min_value_to_save=3)
```

This stage fills the gap left by tactical overrides, which only handle *offensive* opportunities. It prevents Neutral major/minor pieces from being passively sacrificed to cheaper enemy attackers.

#### Trigger condition

For a rescue to fire, a Neutral piece must satisfy **both**:
- Its piece value ≥ 3 (Knights, Bishops, Rooks, Queens — Pawns are intentionally excluded).
- The cheapest enemy piece that can **legally reach** its square has a **strictly lower value**.

```
attacker_value < piece_value  →  losing exchange  →  rescue fires
attacker_value = piece_value  →  equal trade       →  left to Stockfish
attacker_value > piece_value  →  favourable trade  →  left to Stockfish (Neutral loses less)
```

Pawns (value 1) are never rescued — they are expendable and can be re-acquired. Equal-value trades are left to Stockfish's deeper analysis because there may be a tactical reason to allow them.

#### Algorithm

1. Scan all Neutral pieces with value ≥ 3. For each, find the minimum-value enemy attacker that can legally reach it (`ignore_turn=True`).
2. Collect all pieces where `min_attacker_val < piece_val` into a `threatened` list.
3. Sort `threatened` by **descending piece value** — rescue the Queen before the Rook.
4. For the highest-value threatened piece, get its legal moves and filter to squares where `_is_square_safe` returns `True`.
5. Return the **first confirmed-safe escape** as `(from_sq, escape_sq)`.
6. If no safe escape exists for that piece, try the next in the list.
7. If nothing can be saved, return `None` and fall through to Stage 2.

#### Interaction with other stages

| Stage | Relationship |
|-------|-------------|
| Stage 1 Tactical Overrides | Runs **before** rescue. If a Neutral piece can *capture the attacker* (e.g. a Pawn taking a Knight via P5), that fires first. Rescue only fires when the attacker cannot be immediately eliminated. |
| Danger Cycle Evacuation | Runs **before** rescue. A piece already evacuated off a danger rank won't also be rescued. |
| Stage 2 Engine Eval | Only reached if rescue returns `None`. |

#### Example log output

```
[NeutralAI] RESCUE OVERRIDE! Moving Q from (9,4) to (11,6)
(threatened by 1-pt piece, own value 9-pt)
```

---

### Stage 2 — Sub-Board Stockfish Evaluation

If no override or rescue fired, Stockfish evaluates each active window via `_evaluate_subboard`.

#### `_evaluate_subboard` flow

```python
# 1. Build FEN for the 8-rank window
fen = _board_to_fen(gs, lo, hi, ai_owners, active_color, active_color, remove_kings)

# 2. Validate and submit to Stockfish
engine.set_fen_position(fen)
base_cp = engine.get_evaluation()["value"]

# 3. Get top 5 candidate moves
top_moves = engine.get_top_moves(5)

# 4. Translate FEN coordinates → 26-rank coordinates
# FEN rank 1 = lo, FEN rank 8 = lo+7
real_rank = int(fen_rank_char) + rank_lo - 1
real_col  = ord(fen_col_char) - ord('a') + 1
```

The `side_to_move` in `_evaluate_subboard` always equals `active_color` (both base and after evaluations use the same side). Unlike `OpponentAI`'s `get_cp_swing`, the swing here is simply `after_cp − base_cp` without sign inversion.

#### Danger rank filtering

After collecting candidate moves from all windows, each is checked:

```python
if move_pair[1][0] not in danger_ranks:
    candidate_moves[move_pair] += swing
```

Any Stockfish suggestion that lands on a soon-to-be-removed rank is silently discarded. This is a second layer of protection (evacuation in Stage 1 handles *currently on* danger ranks; this handles *would move to* danger ranks).

#### Legal move validation

Every Stockfish suggestion is re-validated by `is_legal_move(from_sq, to_sq, gs)` before entering `candidate_moves`. This is critical because the 8 × 8 FEN slice can include:
- Dummy Kings that don't exist on the real board.
- Pieces that Stockfish encoded as enemies but are actually friendly Neutral pieces.
- Moves that go out of the 26-rank playable boundary.

`is_legal_move` applies full King's Trial rules and rejects any move that is invalid in the true game state.

#### Window evaluation table

| Window | Always evaluated | Hard/Insane only |
|--------|-----------------|-----------------|
| North Board (ranks ~13–23) | ✓ | |
| South Board (ranks ~4–13) | ✓ | |
| Central Board (ranks ~10–17) | | ✓ |

The Central Board anchors at `mid_rank − 3` to `mid_rank + 4` and is evaluated **twice** — once as White, once as Black — to capture bidirectional threats across the board's midline. Both result sets are merged into the same candidate dictionary.

---

### Stage 3 — Final Selection

```python
best_move = max(candidate_moves.items(), key=lambda x: x[1])
return best_move[0]
```

The `candidate_moves` dictionary is keyed by `(from_sq, to_sq)` tuples with accumulated swing as the value. The move with the **maximum total swing** is selected. No random tie-breaking is applied (unlike `OpponentAI`).

**Fallback:** If `candidate_moves` is empty (all Stockfish suggestions were illegal or would land in danger zones), the AI logs a warning and returns `_get_fallback_move` (base class: random legal move).

```
[NeutralAI] No legal candidate moves found from engine! Falling back to random.
```

---

## Dummy King Injection: `_find_safe_dummy_king_square`

Stockfish rejects any FEN without exactly one White King and one Black King. Since Neutral has no King, and player Kings are removed via `remove_kings`, this function places **synthetic (dummy) Kings** in the best available safe squares.

### Placement strategy

| Context | Target squares |
|---------|---------------|
| White Dummy King (want_bottom=True) | Lowest ranks first, columns 1, 8, 2, 7... (corners preferred) |
| Black Dummy King (want_bottom=False) | Highest ranks first, columns 1, 8, 2, 7... |
| **Neutral AI context** | Ranks sorted by proximity to the average rank of all Neutral pieces; middle columns preferred (4, 5, 3, 6...) |

The Neutral-specific override avoids placing dummy Kings at board corners far from the action, which can bias Stockfish toward protecting irrelevant corner squares. Instead, dummy Kings cluster near existing Neutral pieces where evaluation context is most meaningful.

---

## Square Safety Cache

At the start of each turn:

```python
self.current_attacked_squares = self._generate_attacked_squares(gs, ai_owners)
```

This computes the union of:
- All squares reachable by any non-Neutral piece (using `ignore_turn=True`).
- All danger-rank squares (if within 2 cycles of a board shrink).

Calls to `_is_square_safe(..., use_cache=True)` perform a single `sq not in self.current_attacked_squares` O(1) lookup. The full per-piece sliding-ray scan is only triggered when `use_cache=False` (i.e. inside rescue escape checking, where the board is temporarily modified).

---

## Crash Recovery

`choose_move` wraps the entire pipeline in a `try / except` block:

```python
def choose_move(self, gs):
    try:
        return self._choose_move_internal(gs)
    except Exception as e:
        log.error(...)
        try:
            self.engine = Stockfish(path=install_stockfish_engine(), depth=current_depth)
        except Exception as e2:
            log.error(...)
        return self._get_fallback_move(gs)
```

Engine restart preserves the original search depth. Even if restart fails, `_get_fallback_move` (base class: random legal move) guarantees the game never freezes.

---

## Difficulty Scaling

| Feature | Random | Easy | Medium | Hard | Insane |
|---------|--------|------|--------|------|--------|
| Engine enabled | ✗ | ✓ | ✓ | ✓ | ✓ |
| Danger Cycle Evacuation | ✗ | ✓ | ✓ | ✓ | ✓ |
| P1: King Capture | ✗ | ✓ | ✓ | ✓ | ✓ |
| P2: Queen Capture | ✗ | ✗ | ✓ | ✓ | ✓ |
| P3: Safe Pawn Promotion | ✗ | ✓ | ✓ | ✓ | ✓ |
| P4: Rook Capture | ✗ | ✗ | ✓ | ✓ | ✓ |
| P5: Minor Capture (Pawn) | ✗ | ✗ | ✗ | ✓ | ✓ |
| Stage 1.5 Rescue Override | ✗ | ✓ | ✓ | ✓ | ✓ |
| North Board eval | ✗ | ✓ | ✓ | ✓ | ✓ |
| South Board eval | ✗ | ✓ | ✓ | ✓ | ✓ |
| Central Board eval | ✗ | ✗ | ✗ | ✓ | ✓ |

> At **Random** difficulty, `BaseStockfishAI.__init__` skips Stockfish entirely (`self.available = False`). Stage 0 immediately redirects to `_get_fallback_move` for every call.

---

## Key Files

| File | Role |
|------|------|
| `ai/base_stockfish.py` | Stockfish subprocess, FEN builder, dummy-king injection, safety checker, tactical overrides, rescue logic |
| `ai/neutral_ai.py` | Neutral evaluation pipeline: window selection, sub-board eval, candidate accumulation |
| `ai/opponent_ai.py` | Player-opponent AI; more complex (8-step hierarchy, King advance logic) |
| `move_validator.py` | Legal-move generation; `is_legal_move` and `ignore_turn` flag critical for AI correctness |
| `constants.py` | `PIECE_VALUES`, `PROMOTION_COST`, `MAX_PIECE_LIMITS`, `PLAYABLE_MIN/MAX` |
| `game_state.py` | Board state, points treasury, shrink cycle, playable rank bounds |
| `scenes/gameplay.py` | Dispatches `choose_move`; manages turn state-machine and win detection |
