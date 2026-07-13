"""
move_validator.py
=================
Validates legal moves for King's Trial based on game state and piece rules.
"""

from game_state import GameState
from pieces import get_candidate_moves


def get_legal_moves(
    sq: tuple[int, int],
    gs: GameState,
    ignore_turn: bool = False,
) -> list[tuple[int, int]]:
    """
    Return the list of legal (rank, col) destination squares for the
    piece at sq, given the current game state.
    """
    piece = gs.get(*sq)
    if piece is None:
        return []

    # 1. Check if it's this owner's turn
    # Only pieces belonging to the current phase's owner can move.
    if not ignore_turn and piece["owner"] != gs.current_owner():
        return []

    # 2. Get candidate squares based on piece type
    candidates = get_candidate_moves(*sq, piece, gs.board)

    # 3. Filter candidates
    legal = []
    for target_sq in candidates:
        r, c = target_sq
        if not (gs.min_playable_rank <= r <= gs.max_playable_rank):
            continue
            
        target_piece = gs.get(*target_sq)

        # Basic rule: cannot capture own pieces
        if target_piece and target_piece["owner"] == piece["owner"]:
            continue

        # In King's Trial, pieces cannot move into restricted ranks.
        # This is already handled in pieces.py _playable check.

        legal.append(target_sq)

    return legal


def is_legal_move(
    from_sq: tuple[int, int],
    to_sq: tuple[int, int],
    gs: GameState,
    ignore_turn: bool = False,
) -> bool:
    """Check if moving from from_sq to to_sq is currently legal."""
    return to_sq in get_legal_moves(from_sq, gs, ignore_turn=ignore_turn)


def get_all_legal_moves(
    gs: GameState,
    ignore_turn: bool = False,
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """
    Return a list of all legal moves for the current phase owner.
    Each move is a tuple: (from_sq, to_sq)
    """
    owner = gs.current_owner()
    all_moves = []

    for sq, piece in gs.board.items():
        if piece["owner"] == owner or ignore_turn:
            targets = get_legal_moves(sq, gs, ignore_turn=ignore_turn)
            for to_sq in targets:
                all_moves.append((sq, to_sq))

    return all_moves
