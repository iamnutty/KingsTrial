"""
assets.py
=========
AssetManager singleton — loads fonts, sprites, and sounds once,
then serves them by name to all scenes.
"""

from __future__ import annotations
import pygame
import logging

log = logging.getLogger("KingsTrial.assets")


class AssetManager:
    """
    Singleton asset cache.  Call AssetManager.instance() to get the
    shared instance.  Must be initialised after pygame.init().
    """

    _instance: "AssetManager | None" = None

    def __init__(self) -> None:
        self._fonts:   dict[tuple, pygame.font.Font] = {}
        self._sprites: dict[str, pygame.Surface]     = {}
        self._sounds:  dict[str, object]             = {}   # pygame.mixer.Sound stubs

    # ── Singleton ──────────────────────────────────────────────────────────
    @classmethod
    def instance(cls) -> "AssetManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Clear the cache (call on restart / hot-reload)."""
        cls._instance = None

    # ── Fonts ──────────────────────────────────────────────────────────────
    def get_font(
        self,
        name: str  = "dejavusansmono",
        size: int  = 16,
        bold: bool = False,
    ) -> pygame.font.Font:
        """Return a cached SysFont.  Creates it on first request."""
        key = (name, size, bold)
        if key not in self._fonts:
            self._fonts[key] = pygame.font.SysFont(name, size, bold=bold)
            log.debug("Font loaded: %s %dpx bold=%s", name, size, bold)
        return self._fonts[key]

    # ── Sprites ───────────────────────────────────────────────────────────
    def get_sprite(self, name: str) -> pygame.Surface | None:
        """Return a cached sprite surface by name, or None if not loaded."""
        return self._sprites.get(name)

    def load_sprite(self, name: str, path: str) -> pygame.Surface:
        """Load and cache a sprite from file."""
        surf = pygame.image.load(path).convert_alpha()
        self._sprites[name] = surf
        log.debug("Sprite loaded: %s from %s", name, path)
        return surf

    # ── Piece sprites ─────────────────────────────────────────────────────
    # Naming convention for keys: "piece_{owner}_{type}" e.g. "piece_white_K"
    # PNG files: assets/pieces/{owner}-{piece_name}.png
    _PIECE_NAME_MAP = {
        "K": "king",
        "Q": "queen",
        "R": "rook",
        "B": "bishop",
        "N": "knight",
        "P": "pawn",
    }

    def load_piece_sprites(self, pieces_dir: str, tile_size: int) -> None:
        """
        Load all piece PNGs from *pieces_dir* (assets/pieces/), scale each
        to *tile_size* × *tile_size*, and cache under ``piece_{owner}_{type}``.

        Missing files are skipped with a warning so the game still launches.
        """
        import os
        for owner in ("white", "black", "neutral"):
            for ptype, pname in self._PIECE_NAME_MAP.items():
                fname   = f"{owner}-{pname}.png"
                fpath   = os.path.join(pieces_dir, fname)
                key     = f"piece_{owner}_{ptype}"
                if os.path.exists(fpath):
                    try:
                        raw  = pygame.image.load(fpath).convert_alpha()
                        surf = pygame.transform.smoothscale(raw, (tile_size, tile_size))
                        self._sprites[key] = surf
                        log.debug("Piece sprite loaded: %s", key)
                    except Exception as exc:
                        log.warning("Could not load piece sprite %s: %s", fpath, exc)
                else:
                    log.warning("Piece sprite missing: %s", fpath)

    def get_piece_sprite(
        self,
        owner: str,
        piece_type: str,
        tile_size: int | None = None,
    ) -> "pygame.Surface | None":
        """
        Return the cached piece sprite for *owner* + *piece_type*.

        If *tile_size* is provided and differs from the cached size the sprite
        is rescaled on the fly (results are NOT re-cached — call
        ``load_piece_sprites`` at the right size at startup).
        """
        key  = f"piece_{owner}_{piece_type}"
        surf = self._sprites.get(key)
        if surf is None:
            return None
        if tile_size is not None and surf.get_width() != tile_size:
            return pygame.transform.smoothscale(surf, (tile_size, tile_size))
        return surf

    # ── Sounds (Step 21 stub) ──────────────────────────────────────────────
    def get_sound(self, name: str) -> object | None:
        """Return a cached sound by name, or None if not loaded."""
        return self._sounds.get(name)

    def load_sound(self, name: str, path: str) -> object:
        """Load and cache a pygame sound from file."""
        snd = pygame.mixer.Sound(path)
        self._sounds[name] = snd
        log.debug("Sound loaded: %s from %s", name, path)
        return snd
