"""Pure state machine for the red boundary-line safety stop. No hardware IO here.

A red line marks the limits of the allowed driving area: this class only tracks whether the
wheels should currently be blocked — it doesn't read any sensor itself.
"""

from enum import Enum, auto


class BoundaryState(Enum):
    FREE = auto()
    BLOCKED = auto()


class BoundaryGuard:
    """Blocks the car once the red boundary line is seen, until it is lifted and repositioned.

    Never releases the block just because the line is no longer seen, since a blocked car cannot
    drive itself away from it — it must be lifted off the surface first, then placed back down
    clear of the line.
    """

    def __init__(self) -> None:
        self._state = BoundaryState.FREE
        self._has_been_lifted = False

    @property
    def is_blocked(self) -> bool:
        return self._state is BoundaryState.BLOCKED

    def update(self, on_boundary: bool, is_lifted: bool) -> tuple[bool, bool]:
        """Call once per loop tick. Returns (just_blocked, just_released) for one-shot side effects."""
        just_blocked = False
        just_released = False

        if self._state is BoundaryState.FREE:
            if on_boundary:
                self._state = BoundaryState.BLOCKED
                self._has_been_lifted = False
                just_blocked = True
        else:  # BLOCKED
            if is_lifted:
                self._has_been_lifted = True
            elif self._has_been_lifted and not on_boundary:
                self._state = BoundaryState.FREE
                self._has_been_lifted = False
                just_released = True

        return just_blocked, just_released
