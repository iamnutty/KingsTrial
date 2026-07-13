import logging
import sys
import os

from game_state import GameState
from config import GameConfig
from layout_reader import load_board_state
from ai.opponent_ai import OpponentAI
from ai.neutral_ai import NeutralAI

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

config = GameConfig.load()
path = os.path.join("assets", "maps", config.layout_file)
initial_pieces = load_board_state(path)

gs = GameState(initial_pieces, time_control="5+10")
print("Initial owner:", gs.current_owner())

ai = OpponentAI(elo=1710, depth=10, difficulty="medium")
print("Opponent AI available?", ai.available)

move = ai.choose_move(gs)
print("Opponent AI move:", move)

gs.advance_phase()
print("\nPhase advanced. Current owner:", gs.current_owner())
ai2 = NeutralAI(elo=1710, depth=10, difficulty="medium")
move2 = ai2.choose_move(gs)
print("Neutral AI move:", move2)
