"""
ui/theme.py
===========
ThemeManager loads and validates JSON theme files for the board and pieces.
Falls back to hardcoded defaults if JSON parsing fails or values are missing.
"""
import os
import json
import logging

log = logging.getLogger("KingsTrial.theme")

# Built-in absolute fallback in case default.json is corrupted or missing
FALLBACK_THEME = {
    "board": {
        "square_light": (240, 217, 181),
        "square_dark": (181, 136, 99),
        "border": (120, 80, 40),
        "highlight_move": (100, 200, 100, 130),
        "restricted_low": (255, 255, 230, 160),
        "restricted_high": (210, 210, 200, 160),
        "label_text": (220, 220, 220)
    },
    "pieces": {
        "white": {
            "highlight": (255, 215, 0, 160),
            "font_file": "system",
            "font_size": 22,
            "text": (255, 255, 255),
            "badge": (30, 30, 30, 180),
            "chars": { "P": "P", "N": "N", "B": "B", "R": "R", "Q": "Q", "K": "K" }
        },
        "black": {
            "highlight": (255, 215, 0, 160),
            "font_file": "system",
            "font_size": 22,
            "text": (25, 25, 25),
            "badge": (220, 220, 200, 180),
            "chars": { "P": "p", "N": "n", "B": "b", "R": "r", "Q": "q", "K": "k" }
        },
        "neutral": {
            "highlight": (255, 215, 0, 160),
            "font_file": "system",
            "font_size": 22,
            "text": (220, 50, 200),
            "badge": (30, 10, 40, 180),
            "chars": { "P": "P", "N": "N", "B": "B", "R": "R", "Q": "Q", "K": "K" }
        }
    }
}

class ThemeManager:
    def __init__(self, assets_dir: str):
        self.assets_dir = assets_dir
        self.themes_dir = os.path.join(assets_dir, "themes")
        self.current_theme = dict(FALLBACK_THEME)
        self.active_theme_name = "default"
        
    def load_theme(self, theme_name: str) -> None:
        """Load a theme by name (e.g. 'auto', 'cool' or 'default')."""
        if theme_name == "auto" or not theme_name:
            theme_name = "default"
            
        path = os.path.join(self.themes_dir, f"{theme_name}.json")
        if not os.path.exists(path):
            log.error(f"Theme file missing: {path}. Falling back to default.")
            path = os.path.join(self.themes_dir, "default.json")
            
        self.current_theme = self._parse_json(path)
        self.active_theme_name = theme_name
        
        import ui.audio
        if getattr(ui.audio, "manager", None):
            ui.audio.manager.preload_theme_audio(self.current_theme, self.assets_dir)
            
        import ui.renderer
        if hasattr(ui.renderer, "clear_font_cache"):
            ui.renderer.clear_font_cache()
        
    def _parse_json(self, path: str) -> dict:
        import copy
        result = {
            "board": copy.deepcopy(FALLBACK_THEME["board"]),
            "pieces": copy.deepcopy(FALLBACK_THEME["pieces"]),
            "sounds": {},
            "music": []
        }
        
        if not os.path.exists(path):
            return result
            
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            log.error(f"Error parsing theme {path}: {e}")
            return result
            
        board_data = data.get("board", {})
        for k in result["board"]:
            if k in board_data and isinstance(board_data[k], list):
                result["board"][k] = tuple(board_data[k])
                
        piece_data = data.get("pieces", {})
        for owner in ["white", "black", "neutral"]:
            owner_fallback = result["pieces"][owner]
            owner_data = piece_data.get(owner, {})
            for k in owner_fallback:
                if k == "chars":
                    chars_data = owner_data.get("chars", {})
                    for p in ["P", "N", "B", "R", "Q", "K"]:
                        if p in chars_data:
                            val = chars_data[p]
                            if isinstance(val, int):
                                owner_fallback["chars"][p] = chr(val)
                            else:
                                owner_fallback["chars"][p] = str(val)
                elif k in owner_data:
                    val = owner_data[k]
                    if isinstance(val, list):
                        owner_fallback[k] = tuple(val)
                    else:
                        owner_fallback[k] = val
                    
        result["sounds"] = data.get("sounds", {})
        result["music"] = data.get("music", [])
                    
        return result

    def get_board_dict(self) -> dict:
        """Returns the dictionary mapping string keys to RGBA tuples for renderer compat."""
        return self.current_theme["board"]
        
    def get_piece(self, owner: str, key: str):
        return self.current_theme["pieces"][owner][key]

# Global singleton
manager: ThemeManager = None

def setup(assets_dir: str):
    global manager
    manager = ThemeManager(assets_dir)

