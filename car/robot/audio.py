"""A single shared mixer channel that every car sound (effects + voice lines) plays through, so
unrelated sounds never talk over each other and paired sounds (e.g. a honk followed by a spoken
comment about the same event) play out in order instead of on top of each other.
"""

import pygame


class AudioPlayer:
    """Serializes every sound the car plays onto one dedicated `pygame.mixer.Channel`.

    `play_now()` is for standalone events (a button press, a fresh alert) — it always wins,
    immediately stopping whatever is currently playing (and dropping anything that was queued to
    follow it), so the newest event is never left waiting behind a stale one. `play_next()` is for
    a sound that belongs together with what's already playing (e.g. the spoken comment that
    follows a honk about the same event) — it lets the current sound finish undisturbed, then
    plays right after it, never overlapping it. Call `update()` once per drive-loop tick to
    actually start a `play_next()` sound once the channel goes idle — pygame has no
    end-of-playback callback wired up here, so this piggybacks on the loop's existing per-tick
    polling instead.
    """

    def __init__(self) -> None:
        pygame.mixer.init()
        self._channel = pygame.mixer.Channel(0)
        self._pending: pygame.mixer.Sound | None = None

    def play_now(self, sound: pygame.mixer.Sound) -> None:
        self._pending = None
        self._channel.play(sound)

    def play_next(self, sound: pygame.mixer.Sound) -> None:
        if self._channel.get_busy():
            self._pending = sound
        else:
            self._channel.play(sound)

    def update(self) -> None:
        if self._pending is not None and not self._channel.get_busy():
            sound, self._pending = self._pending, None
            self._channel.play(sound)
