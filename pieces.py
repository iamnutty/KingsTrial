"""
pieces.py
=========
Piece movement rules for King's Trial.

This module defines HOW each piece type moves, with all game-specific
variations from standard chess built in:

  PAWN  (player-owned):  Moves AND captures in all 8 directions, 1 square.
                         No en passant. No 2-step first move.
  PAWN  (neutral):       Not currently in use — neutral pieces start as
                         other types per Layout.xlsx.

  KING:                  Moves in all 8 directions, 1 square. No castling.

  KNIGHT:                Standard L-shape moves (2+1). Jumps over pieces.

  BISHOP:                Slides diagonally any distance.

  ROOK:                  Slides along rank or file any distance.

  QUEEN:                 Combines Rook + Bishop slides.

All movement functions accept and return board coordinates as
(rank, col) — both 1-indexed.

The RESTRICTED_RANKS set (1-3, 24-26) is enforced as a filter here:
no generated target square may land in those ranks. Pieces may legally
START there from the initial board setup, but cannot re-enter.

Important: these functions return CANDIDATE squares only — the calling
move_validator.py layer applies additional game-logic filters (e.g.
check for own-piece occupancy, neutrals vs players, etc.)
"""

from constants import (
    BOARD_COLS, BOARD_RANKS,
    PLAYABLE_MIN, PLAYABLE_MAX,
    log,
)


# ---------------------------------------------------------------------------
# Bounds helpers
# ---------------------------------------------------------------------------

def _in_bounds(rank: int, col: int) -> bool:
    """True if (rank, col) is within the physical 8×26 board."""
    return 1 <= rank <= BOARD_RANKS and 1 <= col <= BOARD_COLS


def _playable(rank: int, col: int) -> bool:
    """True if the square is within the physical 1-26 board."""
    return _in_bounds(rank, col)


# ---------------------------------------------------------------------------
# Directional helpers
# ---------------------------------------------------------------------------

# King and player-pawn move in all 8 directions
_ALL_DIRS = [
    (-1, -1), (-1, 0), (-1, 1),
    ( 0, -1),          ( 0, 1),
    ( 1, -1), ( 1, 0), ( 1, 1),
]

# Rook/Queen slide along rank or file
_ROOK_DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

# Bishop/Queen slide diagonally
_BISHOP_DIRS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]

# Knight L-shapes
_KNIGHT_OFFSETS = [
    (-2, -1), (-2, 1),
    (-1, -2), (-1, 2),
    ( 1, -2), ( 1, 2),
    ( 2, -1), ( 2, 1),
]


def _slide(rank: int, col: int, directions: list[tuple]) -> list[tuple]:
    """
    Generate all squares reachable by sliding in the given directions
    from (rank, col). Stops at board edge or restricted rank (call-site
    must still filter for own-piece collisions and blocking).
    """
    squares = []
    for dr, dc in directions:
        r, c = rank + dr, col + dc
        while _playable(r, c):
            squares.append((r, c))
            r += dr
            c += dc
    return squares


def _slide_with_blocker(
    rank: int,
    col: int,
    directions: list[tuple],
    board: dict,
    own_owner: str,
    max_range: int | None = None,
) -> list[tuple]:
    """
    Like _slide but stops (inclusive for captures, exclusive for blockers)
    when hitting an occupied square.

    board: { (rank, col) -> piece_dict }
    own_owner: the moving piece's owner — squares with own pieces are excluded.
    max_range: if set, sliding pieces cannot travel further than this many squares.
    """
    squares = []
    for dr, dc in directions:
        r, c = rank + dr, col + dc
        distance = 1
        while _playable(r, c):
            if max_range is not None and distance > max_range:
                break
                
            target = board.get((r, c))
            if target is not None:
                # Occupied — can capture if it's not our own piece
                if target["owner"] != own_owner:
                    squares.append((r, c))
                break   # either way, can't slide further
            squares.append((r, c))
            r += dr
            c += dc
            distance += 1
    return squares


# ---------------------------------------------------------------------------
# Per-piece candidate square generators
# ---------------------------------------------------------------------------

def pawn_moves(rank: int, col: int, owner: str, board: dict) -> list[tuple]:
    """
    Player pawns move 1 square forward (empty square) and capture 1 square diagonally forward.
    White moves UP (rank + 1), Black moves DOWN (rank - 1).
    Neutral pawns consider both UP and DOWN as 'forward' so they can attack either player.
    """
    candidates = []
    
    if owner == "white":
        forward_dirs = [1]
    elif owner == "black":
        forward_dirs = [-1]
    else:
        forward_dirs = [1, -1]  # Neutral pawns can move/capture both ways
        
    for dr in forward_dirs:
        # Move forward 1 step into empty square
        r_fwd, c_fwd = rank + dr, col
        if _playable(r_fwd, c_fwd):
            target = board.get((r_fwd, c_fwd))
            if target is None:
                candidates.append((r_fwd, c_fwd))
                
        # Capture diagonally 1 step
        for dc in [-1, 1]:
            r_diag, c_diag = rank + dr, col + dc
            if _playable(r_diag, c_diag):
                target = board.get((r_diag, c_diag))
                if target is not None and target["owner"] != owner:
                    candidates.append((r_diag, c_diag))
                    
    return candidates


def king_moves(rank: int, col: int, owner: str, board: dict) -> list[tuple]:
    """
    King: 1 square in all 8 directions. No castling.
    """
    candidates = []
    for dr, dc in _ALL_DIRS:
        r, c = rank + dr, col + dc
        if not _playable(r, c):
            continue
        target = board.get((r, c))
        if target is None or target["owner"] != owner:
            candidates.append((r, c))
    return candidates


def knight_moves(rank: int, col: int, owner: str, board: dict) -> list[tuple]:
    """
    Knight: L-shape jumps (2+1). Jumps over blocking pieces.
    """
    candidates = []
    for dr, dc in _KNIGHT_OFFSETS:
        r, c = rank + dr, col + dc
        if not _playable(r, c):
            continue
        target = board.get((r, c))
        if target is None or target["owner"] != owner:
            candidates.append((r, c))
    return candidates


def bishop_moves(rank: int, col: int, owner: str, board: dict) -> list[tuple]:
    """
    Bishop: slides diagonally (max 7 squares).
    """
    return _slide_with_blocker(rank, col, _BISHOP_DIRS, board, owner, max_range=7)


def rook_moves(rank: int, col: int, owner: str, board: dict) -> list[tuple]:
    """
    Rook: slides along rank or file (max 7 squares). No castling.
    """
    return _slide_with_blocker(rank, col, _ROOK_DIRS, board, owner, max_range=7)


def queen_moves(rank: int, col: int, owner: str, board: dict) -> list[tuple]:
    """
    Queen: combines rook + bishop slides (max 7 squares).
    """
    return _slide_with_blocker(rank, col, _ROOK_DIRS + _BISHOP_DIRS, board, owner, max_range=7)


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

# Maps piece type character → move generator function
MOVE_GENERATORS = {
    "P": pawn_moves,
    "K": king_moves,
    "N": knight_moves,
    "B": bishop_moves,
    "R": rook_moves,
    "Q": queen_moves,
}


def get_candidate_moves(rank: int, col: int, piece: dict, board: dict) -> list[tuple]:
    """
    Return candidate destination squares for the piece at (rank, col).
    Does NOT check for game-logic validity (whose turn it is, check, etc.).
    That is handled by move_validator.py.
    """
    ptype  = piece["type"]
    owner  = piece["owner"]

    gen = MOVE_GENERATORS.get(ptype)
    if gen is None:
        log(f"pieces: no move generator for type '{ptype}'")
        return []

    return gen(rank, col, owner, board)
