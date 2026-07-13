import sys
sys.path.append(r"c:\Projects\KingsTrial")
from game_state import GameState, make_piece

print("=== Testing Piece Limits ===\n")
pieces = [
    {"rank": 1, "col": 1, "type": "K", "owner": "white"},
    {"rank": 2, "col": 1, "type": "N", "owner": "white"},
    {"rank": 2, "col": 2, "type": "N", "owner": "white"},
    {"rank": 3, "col": 1, "type": "P", "owner": "white"},
]

gs = GameState(pieces)
gs.points["white"] = 100

# Put some pieces in respawn pool
gs.respawn_pool["white"].append(make_piece("N", "white"))
gs.respawn_pool["white"].append(make_piece("B", "white"))

# Try to spawn a Knight (should fail, 2 already on board)
res = gs.execute_respawn("N", (4,1))
print(f"Respawn Knight (2 on board): {res}")

# Try to spawn a Bishop (should succeed, 0 on board, in pool)
res = gs.execute_respawn("B", (4,2))
print(f"Respawn Bishop (0 on board): {res}")

# Try to spawn infinite pawns (0 in pool)
res = gs.execute_respawn("P", (4,3))
print(f"Respawn Pawn (0 in pool): {res}")

# Try to promote pawn to Knight (should fail, 2 on board)
res = gs.execute_promotion((3,1), "N")
print(f"Promote Pawn to Knight (2 on board): {res}")

# Try to promote pawn to Rook (should succeed, 0 on board)
res = gs.execute_promotion((3,1), "R")
print(f"Promote Pawn to Rook (0 on board): {res}")

# Check points (100 - 3(Bishop) - 1(Pawn) - 6(Rook promotion cost) = 90)
print(f"\nFinal White points: {gs.points['white']}")
print("Expected points: 90")
