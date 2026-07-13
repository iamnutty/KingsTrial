import os
import pygame
import logging

log = logging.getLogger("KingsTrial.audio")

class AudioManager:
    """
    Handles playback of sound effects and background music for themes.
    If a theme tries to play a missing or corrupted file, this manager catches
    the exception, logs it, and silently ignores the request (Play Nothing fallback).
    """

    def __init__(self):
        self.sounds: dict[str, list[pygame.mixer.Sound]] = {}
        self.music_queue: list[str] = []
        self.sfx_volume: float = 1.0
        self.music_volume: float = 0.0
        self.current_music_index = 0

        self.MUSIC_END_EVENT = pygame.USEREVENT + 1

        # Try to initialize mixer if not already done
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            pygame.mixer.music.set_endevent(self.MUSIC_END_EVENT)
        except pygame.error as e:
            log.warning("Audio mixer failed to initialize: %s. Audio disabled.", e)

    def update_settings(self, sfx_level: int, music_level: int):
        levels = {0: 0.0, 1: 0.35, 2: 0.60, 3: 1.0}
        self.sfx_volume = levels.get(sfx_level, 1.0)
        old_music_vol = self.music_volume
        self.music_volume = levels.get(music_level, 0.0)

        if getattr(pygame, 'mixer', None) and pygame.mixer.get_init():
            # Update music volume and playback state
            pygame.mixer.music.set_volume(self.music_volume)
            if self.music_volume == 0.0 and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            elif self.music_volume > 0.0 and old_music_vol == 0.0 and self.music_queue:
                self.play_music()
                
            # Update all preloaded SFX volume
            for sound_list in self.sounds.values():
                for sound in sound_list:
                    sound.set_volume(self.sfx_volume)

    def preload_theme_audio(self, theme_data: dict, assets_dir: str):
        """Called by ThemeManager when a new theme is loaded."""
        self.sounds.clear()
        self.music_queue.clear()
        
        if not getattr(pygame, 'mixer', None) or not pygame.mixer.get_init():
            return

        # 1. Preload SFX
        sounds_dict = theme_data.get("sounds", {})
        for event_key, rel_paths in sounds_dict.items():
            if rel_paths is None:
                continue # Theme explicitly wants silence for this

            if not isinstance(rel_paths, list):
                rel_paths = [rel_paths]
                
            loaded_sounds = []
            for rel_path in rel_paths:
                full_path = os.path.join(assets_dir, rel_path)
                try:
                    sound = pygame.mixer.Sound(full_path)
                    sound.set_volume(self.sfx_volume)
                    loaded_sounds.append(sound)
                    log.debug("Loaded sound '%s': %s", event_key, full_path)
                except Exception as e:
                    log.info("Sound missing or invalid for '%s' (%s). Fallback: Silence.", event_key, full_path)
            
            if loaded_sounds:
                self.sounds[event_key] = loaded_sounds

        # 2. Queue Music
        music_list = theme_data.get("music", [])
        for m_path in music_list:
            if m_path:
                full_path = os.path.join(assets_dir, m_path)
                self.music_queue.append(full_path)

        if self.music_queue:
            log.debug("Loaded %d background tracks.", len(self.music_queue))
        
        # If music is enabled and we just changed theme, restart music
        if self.music_volume > 0.0:
            self.play_music()

    def play_sound(self, event_key: str):
        """Plays a preloaded sound effect, if it exists and SFX is enabled."""
        if self.sfx_volume == 0.0 or not getattr(pygame, 'mixer', None) or not pygame.mixer.get_init():
            return

        sound_list = self.sounds.get(event_key)
        if sound_list:
            import random
            sound = random.choice(sound_list)
            sound.play()
        else:
            log.debug("Triggered sound '%s', but no valid track was loaded.", event_key)

    def play_music(self):
        """Starts the background music loop if tracks are available."""
        if self.music_volume == 0.0 or not self.music_queue:
            return
        
        if not getattr(pygame, 'mixer', None) or not pygame.mixer.get_init():
            return

        track_path = self.music_queue[self.current_music_index]
        try:
            pygame.mixer.music.load(track_path)
            pygame.mixer.music.play(loops=0)
            log.debug("Playing background track %d: %s", self.current_music_index + 1, track_path)
        except Exception as e:
            log.info("Failed to load/play background music '%s': %s. Fallback: Silence.", track_path, e)

    def play_next_track(self):
        """Called automatically when the MUSIC_END_EVENT is fired by Pygame."""
        if self.music_volume == 0.0 or not self.music_queue:
            return
            
        self.current_music_index = (self.current_music_index + 1) % len(self.music_queue)
        self.play_music()


# Global singleton
manager: AudioManager = None
MUSIC_END_EVENT = None

def setup():
    global manager, MUSIC_END_EVENT
    manager = AudioManager()
    MUSIC_END_EVENT = manager.MUSIC_END_EVENT

def update_settings(sfx_level: int, music_level: int):
    if manager:
        manager.update_settings(sfx_level, music_level)

def play_sound(event_key: str):
    if manager:
        manager.play_sound(event_key)

def play_music():
    if manager:
        manager.play_music()

def play_next_track():
    if manager:
        manager.play_next_track()
