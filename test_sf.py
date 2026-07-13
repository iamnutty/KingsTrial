from stockfish import Stockfish
sf = Stockfish(path="c:/Projects/KingsTrial/stockfish/stockfish.exe")

# Position where Black is vasty winning but it's not mate/stalemate
# White has King on h1, Rook on a1. Black has Queen on d2, King on c1.
fen_w = "8/8/8/8/8/8/3q4/R1k4K w - - 0 1"
sf.set_fen_position(fen_w)
eval_w = sf.get_evaluation()

fen_b = "8/8/8/8/8/8/3q4/R1k4K b - - 0 1"
sf.set_fen_position(fen_b)
eval_b = sf.get_evaluation()

print("White to move eval:", eval_w)
print("Black to move eval:", eval_b)
