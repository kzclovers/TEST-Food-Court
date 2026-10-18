"""Audio interface used by main.py.

No sound assets or generated tones exist yet -- every method here is a
silent no-op so the rest of the game can call into a stable interface
now and have real music/sound effects dropped in later without touching
main.py. See SPEC.md's Audio sections for the sounds this will need:
selecting an answer, correct, incorrect, health loss, dictionary
confirmation, mastery, level transitions, failure, and completion, plus
a distinct background music track per enemy.
"""

from __future__ import annotations


class AudioManager:
    def __init__(self) -> None:
        self.music_on = True
        self.sfx_on = True

    def play_sfx(self, name: str) -> None:
        """Play a named sound effect. No-op until sounds are authored."""

    def play_music(self, track: str) -> None:
        """Start a named music track. No-op until music is authored."""

    def stop_music(self) -> None:
        pass

    def set_music_enabled(self, enabled: bool) -> None:
        self.music_on = enabled

    def set_sfx_enabled(self, enabled: bool) -> None:
        self.sfx_on = enabled
