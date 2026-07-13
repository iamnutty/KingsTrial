"""
app.py
======
App — the top-level application class for King's Trial.

Owns the Pygame window, the clock, and the active Scene.
Routes AppState signals from scenes to scene transitions.
Supports both enum-keyed and object-keyed scene transitions
to allow dynamic scenes (e.g. SettingsScene).
"""

from __future__ import annotations
import sys
import logging
import pygame

from scenes.base_scene import Scene, AppState
from scenes.gameplay   import GameplayScene
from scenes.pause      import PauseScene
from scenes.confirm    import ConfirmRestartScene
from scenes.game_over  import GameOverScene
from scenes.menu       import MenuScene
from scenes.settings   import SettingsScene
from scenes.load_game  import LoadGameScene
from scenes.save_game  import SaveGameScene
from scenes.online_lobby    import OnlineLobbyScene
from scenes.online_gameplay import OnlineGameplayScene
from config import GameConfig
import constants as C

log = logging.getLogger("KingsTrial.app")


class App:
    """Main application — owns the window, clock, and scene router."""

    def __init__(self, config: GameConfig | None = None) -> None:
        pygame.init()
        pygame.font.init()
        log.info("Pygame initialised")

        self.config = config or GameConfig.load()
        
        import ui.audio
        ui.audio.setup()
        ui.audio.update_settings(self.config.sfx_volume, self.config.music_volume)

        import os
        import ui.theme
        if getattr(sys, 'frozen', False):
            ext_assets = os.path.join(os.path.dirname(sys.executable), "assets")
            if os.path.exists(ext_assets):
                assets_dir = ext_assets
            else:
                assets_dir = os.path.join(sys._MEIPASS, "assets")
        else:
            assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

        ui.theme.setup(assets_dir)
        ui.theme.manager.load_theme(self.config.theme)

        self.screen = pygame.display.set_mode(
            (C.WINDOW_W, C.WINDOW_H),
            pygame.RESIZABLE | pygame.SCALED,
        )
        log.info("Window: %d×%d", C.WINDOW_W, C.WINDOW_H)

        # Load piece sprites now that the display is initialised (convert_alpha requires a video mode)
        import assets as _assets_mod
        _am = _assets_mod.AssetManager.instance()
        _pieces_dir = os.path.join(assets_dir, "pieces")
        _am.load_piece_sprites(_pieces_dir, C.SQUARE_SIZE)

        self.clock   = pygame.time.Clock()
        self.running = True

        # Build gameplay and overlay scenes
        self._gameplay = GameplayScene(self.config, self.screen)
        self._menu     = MenuScene(self, self.screen)
        self._settings = SettingsScene(self, self.screen, back_state=AppState.MENU)
        self._loader   = LoadGameScene(self, self.screen, back_state=AppState.MENU)
        self._saver    = SaveGameScene(self, self.screen, self._gameplay,
                                       back_state=AppState.PAUSED)

        self._scenes: dict[AppState, Scene] = {
            AppState.MENU:            self._menu,
            AppState.GAMEPLAY:        self._gameplay,
            AppState.PAUSED:          PauseScene(self._gameplay, self.screen),
            AppState.CONFIRM_RESTART: ConfirmRestartScene(self._gameplay, self.screen),
            AppState.GAME_OVER:       GameOverScene(self._gameplay, self.screen),
            AppState.LOAD_GAME:       self._loader,
            AppState.SAVE_GAME:       self._saver,
            AppState.ONLINE_LOBBY:    OnlineLobbyScene(self, self.screen),
        }

        # Holds session data set by OnlineLobbyScene before transitioning
        self.online_session: dict | None = None

        # Start at the main menu
        self._state: AppState = AppState.MENU
        self._active_scene_obj: Scene = self._menu
        self._active_scene_obj.on_enter(None)

    # ── Main loop ─────────────────────────────────────────────────────────

    def run(self) -> None:
        """Enter the main game loop."""
        while self.running:
            dt = self.clock.tick(60) / 1000.0

            # ── Events ────────────────────────────────────────────────────
            for event in pygame.event.get():
                import ui.audio
                if hasattr(ui.audio, "MUSIC_END_EVENT") and event.type == ui.audio.MUSIC_END_EVENT:
                    ui.audio.play_next_track()

                if event.type == pygame.QUIT:
                    self.running = False
                    break

                result = self._active_scene_obj.handle_event(event)
                if result is not None:
                    self._transition(result)
                    break

            # ── Update ────────────────────────────────────────────────────
            result = self._active_scene_obj.update(dt)
            if result is not None:
                self._transition(result)

            # ── Render ─────────────────────────────────────────────────────
            self._active_scene_obj.render(self.screen)
            pygame.display.flip()

        pygame.quit()
        sys.exit(0)

    # ── State transitions ─────────────────────────────────────────────────

    def _transition(self, new_state: AppState | str) -> None:
        """Transition to a registered scene by AppState enum."""
        if new_state == AppState.QUIT:
            self.running = False
            return

        if new_state == AppState.GAMEPLAY:
            import ui.theme
            ui.theme.manager.load_theme(self.config.theme)
            
            # Rebuild gameplay if config changed from settings
            if self._gameplay.config is not self.config:
                self._gameplay.quit_ais()
                self._gameplay = GameplayScene(self.config, self.screen)
                self._scenes[AppState.GAMEPLAY] = self._gameplay
                self._scenes[AppState.PAUSED]   = PauseScene(self._gameplay, self.screen)
                self._scenes[AppState.CONFIRM_RESTART] = ConfirmRestartScene(self._gameplay, self.screen)
                self._scenes[AppState.GAME_OVER] = GameOverScene(self._gameplay, self.screen)

        if new_state == AppState.LOAD_GAME:
            # Dynamic back_state: from PAUSED → return to PAUSED; else MENU
            self._loader.back_state = (
                AppState.PAUSED if self._state == AppState.PAUSED else AppState.MENU
            )

        if new_state == AppState.ONLINE_GAMEPLAY:
            # Build a fresh OnlineGameplayScene from the session the lobby prepared
            if self.online_session is None:
                log.warning("ONLINE_GAMEPLAY transition with no online_session — going to MENU")
                new_state = AppState.MENU
            else:
                import ui.theme
                ui.theme.manager.load_theme(self.config.theme)  # keep local theme
                online_scene = OnlineGameplayScene(self.online_session, self.screen)
                self._scenes[AppState.ONLINE_GAMEPLAY] = online_scene
                self.online_session = None  # consumed

        target = self._scenes.get(new_state)
        if target is None:
            log.warning("No scene registered for %s", new_state)
            return

        if new_state in (AppState.PAUSED, AppState.CONFIRM_RESTART, AppState.GAME_OVER):
            if hasattr(target, 'gameplay'):
                target.gameplay = self._active_scene_obj

        log.info("Transition: %s → %s", self._state, new_state)
        self._active_scene_obj.on_exit()
        # BUG-014 FIX: Store the previous state BEFORE overwriting self._state so
        # that on_enter() receives the correct origin state, not the destination.
        # This ensures GameplayScene.on_enter() can correctly detect when the
        # player is arriving from CONFIRM_RESTART and fires the AI kickstart.
        prev_state = self._state
        self._state = new_state
        self._active_scene_obj = target
        self._active_scene_obj.on_enter(prev_state)

    def _transition_to_scene(self, scene: Scene, key: object) -> None:
        """
        Transient scene transition (e.g. Settings opened from Menu).
        Does not register into _scenes permanently.
        """
        log.info("Transient transition → %s", type(scene).__name__)
        self._active_scene_obj.on_exit()
        self._state = key
        self._active_scene_obj = scene
        self._active_scene_obj.on_enter(None)

    @property
    def _active_scene(self) -> Scene:
        return self._active_scene_obj
