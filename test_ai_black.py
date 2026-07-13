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
# Phase 0: White
print("Phase 0:", gs.current_owner())
gs.execute_move((7, 5), (8, 4))
gs.advance_phase()

# Phase 1: Neutral
print("Phase 1:", gs.current_owner())
gs.execute_move((11, 7), (9, 6))
gs.advance_phase()

# Phase 2: Black
print("Phase 2:", gs.current_owner())
ai = OpponentAI(elo=1710, depth=10, difficulty="medium")
move = ai.choose_move(gs)
print("Opponent AI move:", move)
