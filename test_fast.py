from game_state import GameState

def _fast_is_attacked(sq: tuple[int, int], gs, enemy_owners: tuple[str, ...]) -> bool:
    r, c = sq
    
    # 1. Knights
    for dr, dc in [(2, 1), (2, -1), (-2, 1), (-2, -1), (1, 2), (1, -2), (-1, 2), (-1, -2)]:
        p = gs.board.get((r + dr, c + dc))
        if p and p["owner"] in enemy_owners and p["type"] == "N": return True
            
    # 2. Kings
    for dr in [-1, 0, 1]:
        for dc in [-1, 0, 1]:
            if dr == 0 and dc == 0: continue
            p = gs.board.get((r + dr, c + dc))
            if p and p["owner"] in enemy_owners and p["type"] == "K": return True
                
    # 3. Sliders (Rook, Bishop, Queen)
    dirs = [
        (1, 0, ("R", "Q")), (-1, 0, ("R", "Q")),
        (0, 1, ("R", "Q")), (0, -1, ("R", "Q")),
        (1, 1, ("B", "Q")), (1, -1, ("B", "Q")),
        (-1, 1, ("B", "Q")), (-1, -1, ("B", "Q"))
    ]
    for dr, dc, attacker_types in dirs:
        for dist in range(1, 8):
            tr, tc = r + dr * dist, c + dc * dist
            if not (gs.min_playable_rank <= tr <= gs.max_playable_rank and 1 <= tc <= 8): break
            p = gs.board.get((tr, tc))
            if p:
                if p["owner"] in enemy_owners and p["type"] in attacker_types: return True
                break
                
    # 4. Pawns
    for owner in enemy_owners:
        drs = [-1] if owner == "white" else ([1] if owner == "black" else [-1, 1])
        for dr in drs:
            for dc in [-1, 1]:
                p = gs.board.get((r + dr, c + dc))
                if p and p["owner"] == owner and p["type"] == "P": return True
                
    return False

class DummyGS:
    def __init__(self):
        self.board = {
            (4, 4): {"owner": "white", "type": "P"},
            (6, 4): {"owner": "black", "type": "P"},
            (5, 7): {"owner": "neutral", "type": "N"},
            (2, 5): {"owner": "black", "type": "R"},
            (8, 8): {"owner": "black", "type": "B"}
        }
        self.min_playable_rank = 1
        self.max_playable_rank = 30

gs = DummyGS()
# 5,5 is attacked by white P at 4,4?
# white pawn attacks r+1. from 4,4 it attacks 5,3 and 5,5. YES.
print("5,5 attacked by white:", _fast_is_attacked((5,5), gs, ("white",)))

# 5,5 is attacked by black P at 6,4?
# black pawn attacks r-1. from 6,4 it attacks 5,3 and 5,5. YES.
print("5,5 attacked by black:", _fast_is_attacked((5,5), gs, ("black",)))

# 5,5 is attacked by neutral N at 5,7? NO. 
# Knight at 5,7 attacks 6,5, 4,5, 7,6, 3,6... wait, (5+0, 7-2) = 5,5. Knight jumps (0, -2)? No! Knight jumps 1,2 or 2,1.
print("5,5 attacked by neutral N:", _fast_is_attacked((5,5), gs, ("neutral",))) # Should be False

# 5,5 is attacked by black R at 2,5?
# 2,5 to 5,5 is a rank jump of 3. YES.
print("5,5 attacked by black R:", _fast_is_attacked((5,5), gs, ("black",)))

# 5,5 is attacked by black B at 8,8?
# 8,8 to 5,5 is a diagonal of 3. YES.
print("5,5 attacked by black B:", _fast_is_attacked((5,5), gs, ("black",)))

