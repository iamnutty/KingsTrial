"""
layout_reader.py
================
Parses the Layout.csv file to produce the initial board state
for King's Trial.

Spreadsheet format (as observed):
  - Row 1      : File headers ('a','b',...,'h') — skip
  - Row 28     : Duplicate file headers            — skip
  - Rows 2–27  : Game ranks. Column I holds the rank NUMBER (1–26).
                 Columns A–H hold piece codes or None.
  - Columns A–H map to files a–h (1–8)

Piece code convention:
  '1X'  → White piece, type X   (e.g. '1P' = white pawn, '1K' = white king)
  '2X'  → Black piece, type X   (e.g. '2P' = black pawn, '2K' = black king)
  'NX'  → Neutral piece, type X (e.g. 'NP' = neutral pawn, 'NN' = neutral knight)

Type letters follow standard chess notation:
  P = Pawn, N = Knight, B = Bishop, R = Rook, Q = Queen, K = King

Output: a list of piece dicts compatible with ui/renderer.draw_pieces():
  { 'rank': int, 'col': int, 'type': str, 'owner': str }
  where owner is 'white', 'black', or 'neutral'.
"""

import csv
from constants import log, BOARD_COLS, BOARD_RANKS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LAYOUT_FILE  = "TEST_CSV.csv"
RANK_COL_IDX = 9                # Column I (1-indexed) holds the rank number

# Piece type mapping from code letter → our internal type string
_TYPE_MAP = {
    "P": "P",   # Pawn
    "N": "N",   # Knight
    "B": "B",   # Bishop
    "R": "R",   # Rook
    "Q": "Q",   # Queen
    "K": "K",   # King
}

# Piece owner mapping from prefix character
_OWNER_MAP = {
    "1": "white",
    "2": "black",
    "N": "neutral",
}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_cell(cell_value: str) -> dict | None:
    """
    Parse a single cell value into a piece descriptor dict (type + owner),
    or return None if the cell is empty / unrecognised.

    Expected formats: '1P', '2K', 'NB', 'NN', 'NR', etc.
    """
    if not cell_value:
        return None

    code = str(cell_value).strip()

    if len(code) < 2:
        log(f"layout_reader: skipping unrecognised cell '{code}'")
        return None

    prefix     = code[0]        # '1', '2', or 'N'
    type_letter = code[1]       # 'P', 'N', 'B', 'R', 'Q', 'K'

    owner = _OWNER_MAP.get(prefix)
    ptype = _TYPE_MAP.get(type_letter)

    if owner is None or ptype is None:
        log(f"layout_reader: unrecognised code '{code}' — skipping")
        return None

    return {"type": ptype, "owner": owner}


def load_board_state(filepath: str = LAYOUT_FILE) -> list[dict]:
    """
    Load and parse the CSV layout file.

    Returns a list of piece dicts:
        [{ 'rank': int, 'col': int, 'type': str, 'owner': str }, ...]

    Raises FileNotFoundError if the CSV file is missing.
    """
    log(f"layout_reader: loading '{filepath}'")

    pieces: list[dict] = []

    with open(filepath, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if i >= 28:
                break
            
            # Ensure the row has enough columns for the rank value
            if len(row) <= 8:
                continue

            rank_val_str = row[8].strip()
            if not rank_val_str.isdigit():
                continue

            rank = int(rank_val_str)

            # Validate rank is within our board
            if not (1 <= rank <= BOARD_RANKS):
                log(f"layout_reader: rank {rank} out of range [1,{BOARD_RANKS}] — skipping row")
                continue

            # Columns A-H are indices 0-7 -> game cols 1-8
            for col_idx in range(BOARD_COLS):
                if col_idx < len(row):
                    cell_value = row[col_idx]
                    if not cell_value:
                        continue
                    
                    piece = parse_cell(cell_value)
                    if piece is None:
                        continue

                    piece["rank"] = rank
                    piece["col"]  = col_idx + 1   # 1-indexed (1=A, 2=B, …, 8=H)
                    pieces.append(piece)

                    log(
                        f"layout_reader: placed {piece['owner']:7s} {piece['type']} "
                        f"at rank={rank:2d} col={col_idx+1} "
                        f"(file={'ABCDEFGH'[col_idx]})"
                    )

    log(f"layout_reader: total pieces loaded = {len(pieces)}")
    return pieces


# ---------------------------------------------------------------------------
# Quick self-test (run this file directly to verify parsing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os, sys

    # Ensure we can import constants when run standalone
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    pieces = load_board_state()
    print(f"\nLoaded {len(pieces)} pieces:\n")
    print(f"{'Owner':8s}  {'Type':5s}  {'Rank':5s}  {'Col/File':8s}")
    print("-" * 35)
    for p in sorted(pieces, key=lambda x: (x['rank'], x['col'])):
        file_letter = "ABCDEFGH"[p['col'] - 1]
        print(f"{p['owner']:8s}  {p['type']:5s}  {p['rank']:5d}  {p['col']} ({file_letter})")
