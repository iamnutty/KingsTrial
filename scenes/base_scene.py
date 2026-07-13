"""
scenes/base_scene.py
====================
Abstract Scene base class and AppState enum.

Every screen (gameplay, pause, menu, etc.) is a Scene subclass.
Scenes return an AppState signal from update() to request transitions.
app.py handles state routing.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum, auto
import pygame


class AppState(Enum):
    """All possible application states."""
    GAMEPLAY        = auto()
    PAUSED          = auto()
    CONFIRM_RESTART = auto()
    GAME_OVER       = auto()
    MENU            = auto()   # Step 15
    LOAD_GAME       = auto()   # Step 16
    SAVE_GAME       = auto()   # Step 16 (manual save with filename prompt)
    ONLINE_LOBBY    = auto()   # Play over Web — lobby / setup
    ONLINE_GAMEPLAY = auto()   # Play over Web — active game
    QUIT            = auto()


class Scene(ABC):
    """
    Abstract scene base.

    Lifecycle:
        app passes Pygame events to handle_event() each frame.
        app calls update(dt) each frame.
        app calls render(screen) each frame.
        update() / handle_event() return AppState to signal transition, or None to stay.
    """

    @abstractmethod
    def handle_event(self, event: pygame.event.Event) -> AppState | None:
        """Process one Pygame event.  Return a new state to transition, else None."""
        ...

    @abstractmethod
    def update(self, dt: float) -> AppState | None:
        """Advance logic by dt seconds.  Return a new state to transition, else None."""
        ...

    @abstractmethod
    def render(self, screen: pygame.Surface) -> None:
        """Draw the scene to screen."""
        ...

    def on_enter(self, prev_state: "AppState | None" = None) -> None:
        """Called once when the scene becomes active.  Override as needed."""

    def on_exit(self) -> None:
        """Called once when the scene is deactivated.  Override as needed."""
