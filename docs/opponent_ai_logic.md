# Opponent AI — Decision Logic Reference

## Overview

The `OpponentAI` class (`ai/opponent_ai.py`) drives the single-player AI opponent — either the White or Black player depending on game configuration. It inherits all core infrastructure from `BaseStockfishAI` (`ai/base_stockfish.py`), which manages the Stockfish subprocess, FEN generation, dummy-king injection, and the square-safety oracle.

> **Stockfish Persistence:** A single Stockfish process is opened when the game starts and kept alive for the entire session. The AI does **not** open or close the engine on each turn. If the process crashes, it is seamlessly restarted via `_restart_engine` and play continues without freezing.

### Win Condition Context

The `OpponentAI` represents a player faction whose primary win condition is advancing their **King** to the opposing boundary rank of the playable board:

| Faction | Winning rank | Starting area |
|---------|-------------|---------------|
| White   | `max_playable_rank` (≈ rank 22–23) | Ranks 1–3 |
| Black   | `min_playable_rank` (≈ rank 4–5)   | Ranks 20–22 |

These ranks shrink every 15 cycles (at cycles 15, 30, 45) as the playable board contracts. The AI always tracks the **current** boundary, not the initial one.

---

## Board Context: The 26-Rank Problem

King's Trial is played on an **8 × 26** board. Stockfish only understands **8 × 8** FEN notation. The AI solves this by evaluating a focused **8-rank sliding window** around the area of interest each time it queries the engine.

### Window Selection: `_get_targeted_hotzone`

```
_get_targeted_hotzone(gs, target_sq, attacker_sqs) → (lo, hi)
```

Given a square of interest (e.g. the AI's King, a piece under attack, or a spawn candidate), this method finds the **optimal 8-rank window** by:

1. **Anchoring** the window so that `target_sq` and its ±1 rank neighbourhood (for King stepping) are always fully included.
2. **Scoring** all valid windows by: `(attackers_captured × 100) + total_pieces_included`. The window that captures the most enemy attackers inside it wins.
3. **Clamping** to playable rank bounds if the board is near its shrink limits.

If an enemy attacker falls **outside** the chosen window, it is projected onto the window's edge via a **Dummy Attacker** (see below), ensuring Stockfish still accounts for its threat.

### Dummy Attackers: `get_dummy_attackers`

```python
# Example: enemy Rook at rank 30 threatens King at rank 18.
# Window = [15–22]. Rook is outside → projected to (22, col) as a dummy.
```

Stockfish cannot see pieces outside its 8-rank slice. For every out-of-window enemy that can legally reach `target_sq`, the AI:
- Determines the window edge rank (top or bottom of the slice)
- Places a **copy** of that enemy piece on the edge square in the same column
- Feeds this augmented board to Stockfish
- **Removes the dummies** after evaluation

This means the engine correctly evaluates king-safety and exchange values even when the real threats are many ranks away.

---

## Evaluation Currency: Centipawn Swing

Every move, promotion, or spawn is ultimately scored by a **centipawn swing** value computed by `get_cp_swing`:

```
swing = −(after_cp) − base_cp
```

| Term | Meaning |
|------|---------|
| `base_cp` | Stockfish eval *before* the action, from the AI's perspective (positive = AI winning) |
| `after_cp` | Stockfish eval *after* the action, from the **opponent's** perspective (must be negated) |
| `swing` | Net change in the AI's eval. Positive = improvement for the AI |

### How it works in practice

`get_cp_swing` makes **two** engine calls per action:

1. **Base state** — board is fed as-is with `side_to_move = active_color` (AI's turn).
2. **After state** — the action is applied to the board (move/promote/spawn), board is re-fed with `side_to_move = opp_color` (opponent's turn). Then the action is rolled back.

A **mate score** (`type == "mate"`) is mapped to ±10 000 cp so it always dominates material-only swings.

> **Promotion / Spawn penalty:** Because `get_cp_swing` only measures positional gain, a raw `cost × 50` penalty is subtracted from promotion and spawn swings to account for the points spent from the treasury. This prevents the AI from always spending recklessly.

### Top-Move Accumulator

A `top_moves_so_far` list and `top_swing_so_far` value persist across Steps 4–7, acting as a global best-move register. Multiple moves with equal swing are tracked together and broken with a random pick at execution time, avoiding deterministic play.

---

## Safety Infrastructure

### `_is_square_safe` (inherited from `BaseStockfishAI`)

Checks whether a given square is safe from enemy capture. Checks in this order:

1. **Cache check (O(1)):** At the start of every turn, `_generate_attacked_squares` pre-computes the union of all enemy legal moves plus all danger-rank squares (near-shrink ranks). Static calls use this cache.
2. **Dynamic check (for simulated boards):** When `use_cache=False` (e.g. inside `simulate_is_safe`), the method directly checks Knights, Kings, sliding pieces (R/B/Q), and Pawns — ignoring turn ownership.

Danger ranks (the two outermost playable ranks, when a shrink is ≤ 2 cycles away) are always considered "attacked" regardless of piece placement.

### `simulate_is_safe`

A local closure inside `_choose_move_internal` that:
1. Temporarily applies the move on `gs.board` (mutates in place).
2. Calls `_is_square_safe(..., use_cache=False)` on the resulting board.
3. Rolls back the board to its original state.

Used to confirm that a given move doesn't leave the King exposed **after** the move is made, as opposed to just checking the King's current square.

---

## Timeout Budget

The AI respects a per-turn time budget derived from the clock's increment:

```python
deadline = time.time() + (increment_sec × 2.5)
```

Each step checks `time.time() > deadline` before issuing engine calls. This ensures the AI **always** returns a move within the allotted time even if Steps 4–7 are still running.

---

## Decision Hierarchy: 8 Steps

All 8 steps execute in strict top-to-bottom order. The first step that finds a decisive move **returns immediately** without evaluating lower steps.

---

### STEP 1 — Insta-Win

```python
if move[0] == k_sq and move[1][0] == target_rank:
    return move  # immediate win
```

**Trigger:** The AI's King has a legal move that lands on the current winning rank.

**Why it comes first:** A King reaching the winning rank is the game's primary win condition. No tactical consideration (captures, promotions, spawns) can ever outrank a guaranteed victory, so this check is unconditional and instant.

**Note:** No swing evaluation is performed. The game-over logic in `gameplay.py` handles detection and ending the match.

---

### STEP 2 — Instakill (Capture Enemy King)

```python
if target["type"] == "K" and target["owner"] in enemy_owners:
    return move
```

**Trigger:** Any legal move captures an enemy King.

**Special rule for King-takes-King:** If the AI's *own* King is the capturing piece, `simulate_is_safe` must confirm the destination square is safe (no enemy counter-capture). This prevents the AI from suiciding its King for the capture bonus in a poisoned-square trap.

**Rationale:** Capturing a King scores a **+20 point bonus** (`KING_CAPTURE_BONUS = 20`) and eliminates the opponent's win-condition piece. This is always correct regardless of position.

---

### STEP 3 — King Defense

```python
if k_sq and not _is_square_safe(k_sq, gs, ...):
```

**Trigger:** The King's current square is flagged as unsafe (an enemy can legally move there).

**Process:**

1. Identify all enemy squares whose legal moves include `k_sq` — these are the `attackers`.
2. Call `_get_targeted_hotzone(k_sq, attackers)` to find the most informative 8-rank window, maximising attacker coverage.
3. Build `dummy_attackers` for any attacker outside this window.
4. Filter all legal moves to `candidate_escapes` — moves that pass `simulate_is_safe(k_sq, move)`.
5. Score each escape with `get_cp_swing(move, w_lo, w_hi, dummy_attackers=dummies)`.
6. Return the escape with the **best swing** (random among ties).

**Fallback within Step 3:** If swing evaluation times out before scoring any candidate, the first un-scored escape move is returned anyway. A King out of check is always better than none.

> **Separation from Step 1:** Step 3 only fires when the King is *currently* in danger. Step 1 handles the case where the King *can* immediately reach the winning rank. These are checked independently — a King in check that can also reach the winning rank would be caught by Step 1 first.

---

### Safe Moves Gate

After Step 3 exits (with or without a return), the AI builds:

```python
safe_moves = [m for m in all_legal_moves if simulate_is_safe(k_sq, m)]
```

Every subsequent step only considers moves from `safe_moves`. A move that exposes the King is never chosen by Steps 4–8.

---

### STEP 4 — Major/Minor Tactics (Captures & Evasions)

**What counts as a tactical move:**

| Type | Condition |
|------|-----------|
| **Evasion** | An AI-owned piece (not King, not Pawn) sits on an unsafe square. Any safe move of that piece, or any move by another piece that **defends** that square, qualifies. |
| **Capture** | Any safe move whose destination contains an enemy Major or Minor piece (not King, not Pawn). |

**Scoring:**

Each tactical move is evaluated by `get_cp_swing` using a hotzone anchored at the relevant square. For **captures**, a **material bonus** is added on top of the positional swing:

```python
material_bonus = captured_piece_value × 100
# e.g. capturing a Rook (value=5): +500 bonus cp
```

This infusion ensures a capture of a free Rook will always score above a positional shuffle, even if Stockfish's positional eval is pessimistic about the window.

**Early exit:** If `top_swing_so_far > 400` after evaluating all tactical moves, execute the best immediately. A swing above 400 cp represents roughly a 4-pawn advantage — a decisive gain.

---

### STEP 5 — Promotions

**When it runs:** After Step 4, while the deadline has not been reached.

**Eligibility:** For each non-King AI piece that is **not under attack** (`_is_square_safe` returns `True`):
- Enumerate every piece type whose promotion cost the AI can currently afford (`gs.points[owner] >= cost`).
- Skip types that have hit their piece cap (`MAX_PIECE_LIMITS`).

```
MAX_PIECE_LIMITS = { 'N': 2, 'B': 2, 'R': 1, 'Q': 1 }
PROMOTION_COST   = { 'P': 2, 'N': 4, 'B': 4, 'R': 6, 'Q': 10 }
```

**Scoring:**

```python
swing = get_cp_swing(("PROMOTE", sq, new_type), w_lo, w_hi)
swing -= cost × 50   # treasury penalty
```

The promotion action is applied temporarily to the board, eval is taken, then the action is rolled back — identical to how moves are handled.

**Early exit:** Same as Step 4: if `top_swing_so_far > 400`, execute immediately.

> **Why not promote a piece that's under attack?** Spending points to upgrade a piece that is immediately captured is a wasted action. The `_is_square_safe` guard ensures promotions only fire on safe pieces.

---

### STEP 6 — Positional Play via Engine Query

**Purpose:** Generate good moves in positions where no obvious tactical opportunity exists.

**Process:**

1. Anchor the evaluation window on the King (`target_sq = k_sq`). If no King exists, use the first AI-owned piece.
2. Build the FEN with `_board_to_fen` (no kings removed — both dummy kings injected if needed).
3. Ask Stockfish for its top **3 moves** via `engine.get_top_moves(3)`.
4. Translate each engine move from 8-rank FEN coordinates back to 26-rank board coordinates: `real_rank = lo + fen_rank - 1`.
5. Filter to moves that appear in `safe_moves`.
6. Score each with `get_cp_swing`.

**King Move Bias:**

When a suggested move is a King step, a **proximity bonus** is applied:

```python
# forward move toward winning rank:
progress = (d_max - d) / (d_max - 1)      # 0.0 (start) → 1.0 (one step away)
bonus = 100 + (400 × progress)             # range: +100 near start → +500 near goal
swing += bonus

# backward move (retreating King):
swing -= 50
```

This gradient reward makes the King increasingly aggressive as it nears the goal without forcing it into danger — Stockfish's base swing still captures whether the step is tactically safe.

---

### STEP 7 — Spawning

**Trigger condition:** Runs only if `top_swing_so_far <= 100` (no good move found yet) and the deadline has not passed. Low swing means the position is quiet — spawning may be the best use of points.

**Eligible squares:** Every empty square adjacent (8-directional) to the King within the playable board.

**Eligible piece types:** All major/minor pieces (N, B, R, Q — Pawns excluded) that:
- The AI has enough points to afford (`cost = piece_value`).
- Haven't hit their piece cap.
- For non-Pawn pieces: the target square must be safe (no spawning into an attacked square).

**Scoring:**

```python
swing = get_cp_swing(("SPAWN", piece_type, sq), w_lo, w_hi)
swing -= piece_value × 50    # treasury penalty
```

**Early exit:** If `top_swing_so_far > 300` after all spawn candidates, execute the best spawn immediately.

---

### STEP 8 — Watchdog Execution & Fallbacks

```python
if top_moves_so_far:
    return random.choice(top_moves_so_far)  # random among equally-scored best moves
```

**Primary path:** Execute the highest-swing move accumulated across Steps 4–7. If multiple moves share the top swing, one is chosen at random to prevent predictable patterns.

**Fallback chain:**
1. If `top_moves_so_far` is empty: call `_get_fallback_move`.
2. `_get_fallback_move` filters all legal moves to king-safe ones, then picks randomly from the **cheapest-piece** king-safe moves (Pawns before Knights, etc.) to minimise losses.
3. If no king-safe move exists: return any random legal move.
4. If no legal moves exist at all: return `None` (game state handles stalemate).

---

## Engine Crash Recovery

`choose_move` wraps the entire `_choose_move_internal` call in a `try / except`:

```python
def choose_move(self, gs):
    try:
        return self._choose_move_internal(gs)
    except Exception as e:
        log.error(..., exc_info=True)
        self._restart_engine()
        return self._get_fallback_move(gs)
```

`_restart_engine` preserves the original `depth` from the previous engine instance and reinstantiates Stockfish from scratch. If restart also fails, the error is logged and `_get_fallback_move` still guarantees a valid move is returned.

---

## FEN Translation Details

`_board_to_fen(gs, rank_lo, rank_hi, ai_owners, active_color, side_to_move, remove_kings)`:

1. **Piece mapping:** AI-owned pieces → uppercase (White perspective) or lowercase (Black perspective). Enemy pieces → opposite case.
2. **Danger rank ghosting:** Pieces on the 2 outermost ranks near an imminent shrink are treated as empty squares in the FEN. This prevents Stockfish from planning through squares that will disappear.
3. **King stripping:** Player Kings in `remove_kings` are omitted (used in NeutralAI; in OpponentAI, `remove_kings=[]` is always passed — both dummy kings are injected).
4. **Dummy King Injection:** If neither White nor Black King exists in the window, a dummy is placed at the safest available corner square. Stockfish rejects FENs without both Kings.
5. **FEN assembly:** `"{board_part} {side_to_move} - - 0 1"` — no castling rights, no en-passant.

---

## Difficulty Scaling

| Feature | Random | Easy | Medium | Hard | Insane |
|---------|--------|------|--------|------|--------|
| Engine enabled | ✗ | ✓ | ✓ | ✓ | ✓ |
| Step 1: Insta-Win | ✗ | ✓ | ✓ | ✓ | ✓ |
| Step 2: Instakill | ✗ | ✓ | ✓ | ✓ | ✓ |
| Step 3: King Defense | ✗ | ✓ | ✓ | ✓ | ✓ |
| Step 4: Tactical (captures, evasions) | ✗ | ✓ | ✓ | ✓ | ✓ |
| Step 5: Promotions | ✗ | ✓ | ✓ | ✓ | ✓ |
| Step 6: Positional Engine Play | ✗ | ✓ | ✓ | ✓ | ✓ |
| Step 7: Spawning | ✗ | ✓ | ✓ | ✓ | ✓ |
| Tactical override — Queen capture | ✗ | ✗ | ✓ | ✓ | ✓ |
| Tactical override — Rook capture | ✗ | ✗ | ✓ | ✓ | ✓ |
| Tactical override — Minor capture (Pawn) | ✗ | ✗ | ✗ | ✓ | ✓ |

> At **Random** difficulty, `BaseStockfishAI.__init__` skips Stockfish entirely and all calls fall through to `_get_fallback_move` (pure random legal move).

---

## Key Files

| File | Role |
|------|------|
| `ai/base_stockfish.py` | Stockfish subprocess, FEN builder, dummy-king injection, safety checker, tactical overrides, rescue logic |
| `ai/opponent_ai.py` | Full 8-step decision hierarchy described in this document |
| `ai/neutral_ai.py` | Neutral faction AI; shares `BaseStockfishAI`, simpler pipeline |
| `move_validator.py` | Legal-move generation; `ignore_turn=True` flag used throughout |
| `constants.py` | `PIECE_VALUES`, `PROMOTION_COST`, `MAX_PIECE_LIMITS`, `PLAYABLE_MIN/MAX` |
| `game_state.py` | Board state, points treasury, shrink cycle, win-condition ranks |
| `scenes/gameplay.py` | Dispatches `choose_move`; handles state-machine and win detection |
