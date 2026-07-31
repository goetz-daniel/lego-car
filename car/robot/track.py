"""Pure classification logic for the multi-color line-follower track segments. No hardware IO here."""

from enum import Enum, auto


class TrackSegment(Enum):
    NONE = auto()
    NORMAL = auto()
    BOOST = auto()
    GOAL = auto()


def classify_track_segment(color: int, normal_color: int, boost_color: int, goal_color: int) -> TrackSegment:
    """Maps a detected LEGO Color to the track segment it represents, or NONE if it matches none of them."""
    if color == normal_color:
        return TrackSegment.NORMAL
    if color == boost_color:
        return TrackSegment.BOOST
    if color == goal_color:
        return TrackSegment.GOAL
    return TrackSegment.NONE


class TrackSegmentTracker:
    """Tracks which track segment the car is currently on.

    The differently colored strips are glued seamlessly together, so a single stray tick reading
    an unrecognized or different color right at a color-to-color boundary should not be treated
    as a real segment change. A new segment is only accepted once the same color has been read
    for confirm_ticks consecutive polls in a row; a single noisy tick keeps the last known segment
    instead of flickering.
    """

    def __init__(self, confirm_ticks: int) -> None:
        self._confirm_ticks = max(1, confirm_ticks)
        self._current = TrackSegment.NONE
        self._candidate = TrackSegment.NONE
        self._candidate_streak = 0

    @property
    def current(self) -> TrackSegment:
        return self._current

    def update(self, color: int, normal_color: int, boost_color: int, goal_color: int) -> bool:
        """Call once per loop tick with the freshly detected color. Returns True on a new segment's first tick."""
        detected = classify_track_segment(color, normal_color, boost_color, goal_color)
        if detected is TrackSegment.NONE or detected is self._current:
            self._candidate, self._candidate_streak = TrackSegment.NONE, 0
            return False

        self._candidate_streak = self._candidate_streak + 1 if detected is self._candidate else 1
        self._candidate = detected
        if self._candidate_streak < self._confirm_ticks:
            return False

        self._current = detected
        self._candidate, self._candidate_streak = TrackSegment.NONE, 0
        return True
