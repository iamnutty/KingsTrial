from stockfish import Stockfish
sf = Stockfish(path="c:/Projects/KingsTrial/stockfish/stockfish.exe")

# White to move. Black is up a queen.
fen_w = "8/8/8/8/8/8/3q4/K7 w - - 0 1"
sf.set_fen_position(fen_w)
eval_w = sf.get_evaluation()

# Black to move. Black is up a queen.
fen_b = "8/8/8/8/8/8/3q4/K7 b - - 0 1"
sf.set_fen_position(fen_b)
eval_b = sf.get_evaluation()

print("White to move eval:", eval_w)
print("Black to move eval:", eval_b)
