"""Plays spoken driver comments and narrator instructions using pygame's audio mixer.

Each language is a folder under car/assets/ (e.g. "de"), containing:
- voice/<category>/1.mp3, 2.mp3, ... — spoken from the driver's own perspective, reacting in
  the moment (see COMMENT_CATEGORIES below); one of the numbered clips is picked at random each
  time that category plays, never the same one twice in a row, so add as many variants as you
  like per folder to keep it feeling natural rather than repetitive.
- instructions/<name>.mp3 — a narrator announcing a mode switch; one fixed clip per name, since
  there's exactly one thing to say each time.

Adding a new language is just adding another folder with this same structure (set settings.language
to its name) — nothing here is specific to any one language.
"""

import random
from pathlib import Path

import pygame

from car.robot.audio import AudioPlayer

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

# voice/<category>/ subfolder names; each needs at least a "1.mp3" to satisfy its callers below
COMMENT_CATEGORIES = ("comments", "boundaryline", "losttrack", "crash", "starttrack")
# instructions/<name>.mp3 clips; each is a single fixed file, not a random pick
INSTRUCTION_NAMES = ("freeride", "linefollower")


class VoiceLines:
    """Loads one language's comment/instruction clips once, then plays a random pick per category,
    never immediately repeating the previous pick for that category.
    """

    def __init__(self, language: str, audio_player: AudioPlayer) -> None:
        pygame.mixer.init()
        self._audio = audio_player
        language_dir = ASSETS_DIR / language
        if not language_dir.is_dir():
            raise RuntimeError(f"No voice-line assets for language '{language}' (expected {language_dir}).")

        self._comments: dict[str, list[pygame.mixer.Sound]] = {}
        self._last_comment_index: dict[str, int] = {}
        for category in COMMENT_CATEGORIES:
            category_dir = language_dir / "voice" / category
            files = self._numbered_clips(category_dir)
            if not files:
                raise RuntimeError(f"No comment clips for '{category}' — expected at least {category_dir / '1.mp3'}.")
            self._comments[category] = [pygame.mixer.Sound(str(f)) for f in files]
            self._last_comment_index[category] = -1  # -1 means no clip has played yet

        self._instructions: dict[str, pygame.mixer.Sound] = {}
        for name in INSTRUCTION_NAMES:
            file = language_dir / "instructions" / f"{name}.mp3"
            if not file.is_file():
                raise RuntimeError(f"Missing instruction clip: {file}")
            self._instructions[name] = pygame.mixer.Sound(str(file))

    @staticmethod
    def _numbered_clips(category_dir: Path) -> list[Path]:
        """Returns 1.mp3, 2.mp3, ... in numeric order, or [] if the folder is missing/empty."""
        if not category_dir.is_dir():
            return []
        try:
            return sorted(category_dir.glob("*.mp3"), key=lambda f: int(f.stem))
        except ValueError as exc:
            raise RuntimeError(f"Comment clips in {category_dir} must be named 1.mp3, 2.mp3, ...") from exc

    def play_voice(self, category: str, *, queue: bool = False) -> None:
        """Plays a random clip from category, never the same one twice in a row (unless it's the
        only clip that category has). queue=True waits for whatever is currently playing to finish
        first (a comment following a honk about the same event); the default instead plays it
        immediately, stopping whatever else was playing (a fresh, standalone trigger).
        """
        clips = self._comments[category]
        last_index = self._last_comment_index[category]
        candidates = [i for i in range(len(clips)) if i != last_index] or list(range(len(clips)))
        index = random.choice(candidates)
        self._last_comment_index[category] = index
        sound = clips[index]
        if queue:
            self._audio.play_next(sound)
        else:
            self._audio.play_now(sound)

    def play_instruction(self, name: str) -> None:
        self._audio.play_now(self._instructions[name])
