"""
constants.py
============
Central configuration for King's Trial.
All magic numbers, colour palettes, fonts, board geometry, and enums live here.
Editing this file is the primary way to tweak the look and feel of the game.
"""

import os
import pygame  # imported only for pygame.Color; actual init happens in main.py

# ---------------------------------------------------------------------------
# Board geometry
# ---------------------------------------------------------------------------
BOARD_COLS   = 8        # Files A–H
BOARD_RANKS  = 26       # Ranks 1–26 (rank 1 = White's back rank)

# Playable rank window
PLAYABLE_MIN = 4
PLAYABLE_MAX = 23

# Active sub-board (8×8 slice used for fog-of-war & engine input)
ACTIVE_BOARD_SIZE = 8   # always 8×8

# King anchor rows within the active sub-board (1-indexed)
WHITE_KING_ANCHOR_ROW = 4   # White king sits on row 4 of active board
BLACK_KING_ANCHOR_ROW = 5   # Black king sits on row 5 of active board

# Neutral fallback rank range when no player pieces are in any neutral sub-board
NEUTRAL_FALLBACK_RANKS = list(range(10, 18))  # ranks 10–17 inclusive

# ---------------------------------------------------------------------------
# Pixel layout
# ---------------------------------------------------------------------------
SQUARE_SIZE  = 42       # pixels per board square

# Computed board pixel dimensions
BOARD_PIXEL_W = BOARD_RANKS * SQUARE_SIZE   # wide axis (ranks along horizontal)
BOARD_PIXEL_H = BOARD_COLS  * SQUARE_SIZE   # tall axis  (files along vertical)

# Padding / panel heights
PANEL_TOP_H    = 80     # Height of the top info bar (timers + scores)
PANEL_BOTTOM_H = 220    # Height of the bottom area (move log + status + menu)
SIDE_LABEL_W   = 36     # Width of rank-number gutter on each side of board
FILE_LABEL_H   = 28     # Height of file-letter gutter on top/bottom of board

# Full window size
WINDOW_W = SIDE_LABEL_W + BOARD_PIXEL_W + SIDE_LABEL_W
WINDOW_H = PANEL_TOP_H + FILE_LABEL_H + BOARD_PIXEL_H + FILE_LABEL_H + PANEL_BOTTOM_H

# ---------------------------------------------------------------------------
# Game phase enum (int constants for easy comparison & indexing)
# ---------------------------------------------------------------------------
PHASE_WHITE         = 0   # White player's turn
PHASE_WHITE_NEUTRAL = 1   # Neutral response after white's move
PHASE_BLACK         = 2   # Black player's turn

PHASE_NAMES = {
    PHASE_WHITE:         "White's Turn",
    PHASE_WHITE_NEUTRAL: "Neutral's Turn",
    PHASE_BLACK:         "Black's Turn",
}

# Phase ordering for cycling (Linear 3-Phase Structure)
PHASE_ORDER = [PHASE_WHITE, PHASE_WHITE_NEUTRAL, PHASE_BLACK]

# ---------------------------------------------------------------------------
# Colour themes
# Warm theme  → PHASE_WHITE and PHASE_WHITE_NEUTRAL  (day battle)
# Cool theme  → PHASE_BLACK (night battle)
# ---------------------------------------------------------------------------

# -- Warm theme (used during White & White-Neutral phases) --
WARM = {
    "bg":              (245, 235, 210),   # parchment background
    "square_light":    (240, 217, 181),   # classic light square
    "square_dark":     (181, 136, 99),    # classic dark square
    "restricted_low":  (255, 255, 230, 160),  # whited-out overlay (RGBA)
    "restricted_high": (210, 210, 200, 160),  # greyed-out overlay (RGBA)
    "panel_bg":        (60,  40,  20),    # dark panel background
    "panel_text":      (245, 230, 200),   # warm text
    "label_text":      (80,  55,  30),    # rank/file labels
    "border":          (120, 80,  40),    # board border
    "highlight_sel":   (255, 215, 0,  160),   # selected piece highlight (gold)
    "highlight_move":  (100, 200, 100, 130),  # valid move dot
    "status_text":     (245, 230, 200),
    "menu_btn":        (140, 90,  40),
    "menu_btn_text":   (245, 230, 200),
    "move_log_bg":     (50,  30,  10),
    "move_log_text":   (220, 200, 170),
    "move_log_header": (200, 160, 100),
    "timer_white_bg":  (200, 180, 140),
    "timer_black_bg":  (80,  60,  30),
    "timer_neutral_bg":(160, 100, 60),
    "score_text":      (245, 230, 200),
}

# -- Cool / dark theme (used during Black & Black-Neutral phases) --
# The renderer now queries ui.theme.manager for these colors dynamically.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Grayscale Modern UI Theme
# ---------------------------------------------------------------------------
GRAYSCALE_UI = {
    "bg":              (18,  18,  20),     # Main window background
    "panel_bg":        (28,  30,  34),     # Top bar, bottom bar, dialog boxes
    "panel_text":      (220, 220, 225),    # General UI text
    "border":          (70,  72,  75),     # Borders between panels
    "status_text":     (200, 202, 210),    # Status bar info
    "menu_btn":        (50,  52,  56),     # Neutral modern button
    "menu_btn_text":   (235, 235, 240),    # Bright button text
    "menu_btn_hover":  (75,  78,  82),     # Hovered button background
    "move_log_bg":     (22,  24,  28),     # Darker box for move logs
    "move_log_text":   (210, 215, 220),    # Brighter text for readability
    "move_log_header": (150, 155, 160),
    "timer_white_bg":  (45,  46,  50),
    "timer_black_bg":  (15,  16,  18),
    "timer_neutral_bg":(30,  28,  34),
    "score_text":      (220, 222, 225),
}

# ---------------------------------------------------------------------------
# Piece colours (letter-based rendering)
# ---------------------------------------------------------------------------
PIECE_COLOR_WHITE   = (255, 255, 255)    # White pieces: bright white letters
PIECE_COLOR_BLACK   = (50,  50,  50)     # Black pieces: dark grey letters
PIECE_COLOR_NEUTRAL = (220, 50,  200)    # Neutral pieces: magenta

# Background badge behind each piece letter
BADGE_COLOR_WHITE   = (30,  30,  30,  180)  # dark badge for white letters
BADGE_COLOR_BLACK   = (220, 220, 200, 180)  # light badge for black letters
BADGE_COLOR_NEUTRAL = (30,  10,  40,  180)  # dark-purple badge for neutral

# ---------------------------------------------------------------------------
# Piece point values  (used for scoring, promotion cost, respawn cost)
# ---------------------------------------------------------------------------
PIECE_VALUES = {
    'P': 1,   # Pawn
    'N': 3,   # Knight
    'B': 3,   # Bishop
    'R': 5,   # Rook
    'Q': 9,   # Queen
    'K': 20,  # King (capture bonus)
}

PROMOTION_COST = {p: v + 1 for p, v in PIECE_VALUES.items() if p != 'K'}
# {'P': 2, 'N': 4, 'B': 4, 'R': 6, 'Q': 10}

MAX_PIECE_LIMITS = {
    'N': 2,
    'B': 2,
    'R': 1,
    'Q': 1,
}

# ---------------------------------------------------------------------------
# Starting positions (rank, file) — rank is 1-indexed from White's side
# White staging: ranks 1-3 (can start there, cannot re-enter after leaving)
# ---------------------------------------------------------------------------
START_WHITE_KING  = (1, 5)   # E1
START_WHITE_PAWNS = [(2, 3), (2, 4), (2, 5), (2, 6)]  # C2 D2 E2 F2

START_BLACK_KING  = (20, 4)  # D20
START_BLACK_PAWNS = [(19, 3), (19, 4), (19, 5), (19, 6)]  # C19-F19

START_NEUTRAL_PIECES = [(7, 4), (7, 5), (14, 4), (14, 5)]  # D7 E7 D14 E14 (all pawns initially)

# Respawn squares (used when king is killed)
RESPAWN_WHITE_KING = (4, 5)   # E4
RESPAWN_BLACK_KING = (23, 4)  # D23

# ---------------------------------------------------------------------------
# Clock settings
# ---------------------------------------------------------------------------
TIME_CONTROLS = {
    "2+5":   {"name": "2 Min + 5s", "start_sec": 120, "inc_sec": 5},
    "5+10":  {"name": "5 Min + 10s", "start_sec": 300, "inc_sec": 10},
    "10+20": {"name": "10 Min + 20s", "start_sec": 600, "inc_sec": 20},
}
CLOCK_TIMEOUT_PENALTY = -1    # Points deducted on timeout
AI_MOVE_DELAY_SECONDS = 0.6   # Time in seconds each AI visual phase takes

# ---------------------------------------------------------------------------
# Win / draw conditions
# ---------------------------------------------------------------------------
MAX_CYCLES          = 75      # Full game cycles (W+WN+B+BN = 1 cycle)
WHITE_WIN_RANK      = 22      # White king reaching this rank triggers win
BLACK_WIN_RANK      = 5       # Black king reaching this rank triggers win
KING_CAPTURE_BONUS  = 20      # Points for capturing a king

# ---------------------------------------------------------------------------
# Font configuration  (loaded at runtime in main.py after pygame.init())
# ---------------------------------------------------------------------------
FONT_PATH_MONO  = None    # None = use pygame default (replaced with system font)
FONT_SIZE_PIECE = 22      # Piece letter size
FONT_SIZE_LABEL = 13      # Rank/file label size
FONT_SIZE_UI    = 15      # Generic UI text
FONT_SIZE_TIMER = 22      # Timer digits
FONT_SIZE_SCORE = 14      # Score panel text
FONT_SIZE_LOG   = 14      # Move log text
FONT_SIZE_STATUS= 16      # Game status bar text
FONT_SIZE_BTN   = 14      # Menu button text

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
import logging as _logging

_logger = _logging.getLogger("KingsTrial")

def log(msg: str) -> None:
    """
    Backward-compatible log helper.
    Delegates to the standard Python logging subsystem.
    """
    _logger.debug(msg)
