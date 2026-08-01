"""Plays the car's sound effects (e.g. honking) using pygame's audio mixer."""

from pathlib import Path

import pygame

from car.robot.audio import AudioPlayer

EFFECTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "effects"


class CarSound:
    def __init__(self, honk_file: str, boost_file: str, audio_player: AudioPlayer) -> None:
        # audio_player's own construction already initialized the mixer
        self._audio = audio_player
        self._honk = pygame.mixer.Sound(str(EFFECTS_DIR / honk_file))
        self._boost = pygame.mixer.Sound(str(EFFECTS_DIR / boost_file))

    def play_honk(self) -> None:
        """A standalone alert — always takes over immediately, even mid another sound."""
        self._audio.play_now(self._honk)

    def play_boost(self) -> None:
        self._audio.play_now(self._boost)
