"""Pure drive math: turns gamepad input into independent left/right motor speeds. No hardware/IO here."""

from dataclasses import dataclass
from enum import Enum, auto

from car.robot.track import TrackSegment


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def analog_amount(raw_value: float, rest: float, peak: float) -> float:
    """Normalizes a raw axis reading into 0 (rest) .. 1 (fully pressed), given the endpoints observed
    during gamepad calibration. Used for analog triggers, which report a continuous range rather than
    a simple pressed/released button.
    """
    span = peak - rest
    if span == 0:
        return 0.0
    return clamp((raw_value - rest) / span, 0.0, 1.0)


def throttle_for_boost(boost_amount: float, base_speed_percent: float, max_speed_percent: float) -> float:
    """Picks the target throttle (0..1) by interpolating from base to max speed as boost_amount goes 0..1.

    boost_amount is continuous for an analog trigger (proportional boost) or a plain 0.0/1.0 for a
    digital button (fixed max speed); the motor's own acceleration/deceleration ramps handle the
    transition smoothly either way.
    """
    boost_amount = clamp(boost_amount, 0.0, 1.0)
    return (base_speed_percent + (max_speed_percent - base_speed_percent) * boost_amount) / 100


def arcade_drive(forward: float, turn: float, throttle: float, turn_scale: float) -> tuple[float, float]:
    """Mixes forward/backward (-1/0/1) and turn (-1..1) input with throttle (0..1) into left/right motor speeds (-100..100).

    turn_scale weakens the turn input relative to forward/backward, e.g. 0.5 makes steering half as fast.
    """
    turn = turn * turn_scale
    left = clamp(forward + turn, -1.0, 1.0)
    right = clamp(forward - turn, -1.0, 1.0)
    return left * throttle * 100, right * throttle * 100


@dataclass(frozen=True)
class TurnCommand:
    """A relative, in-place pivot: positive degrees turns right, negative turns left."""

    degrees: float


class _Phase(Enum):
    DRIVE = auto()
    LOOK_STRAIGHT = auto()
    LOOK_SMALL_LEFT = auto()
    LOOK_SMALL_RIGHT = auto()
    LOOK_LEFT = auto()
    LOOK_RIGHT = auto()


class LineFollower:
    """Continuous-driving line following for a single downward-facing color sensor.

    Drives straight while blue/green/white is seen. On loss: halts, dwells dead ahead, then a
    small left/right nudge, then (if that fails) a much wider sweep, stopping and resuming
    straight the instant any look finds the line again. If the wide sweep also fails, update()
    reports gave_up and the caller repositions the car by hand — no backing up or retrying.
    """

    def __init__(
        self,
        small_scan_degrees: float,
        scan_degrees: float,
        look_straight_ticks: int,
    ) -> None:
        self._small_scan_degrees = small_scan_degrees
        self._scan_degrees = scan_degrees
        self._look_straight_ticks = max(1, look_straight_ticks)

        self._phase = _Phase.DRIVE
        self._phase_ticks_left = 0

    @property
    def is_searching(self) -> bool:
        return self._phase is not _Phase.DRIVE

    def update(self, segment: TrackSegment, motor_done: bool) -> tuple[bool, TurnCommand | None, bool]:
        """Call once per tick. Returns (drive_straight, command, gave_up): drive_straight is True
        the instant the line is (re)seen (caller should call motors.drive(), which also cancels
        any turn still in flight); command is a new turn to issue this tick, or None; gave_up is
        whether even the wide scan couldn't relocate the line.
        """
        on_track = segment is not TrackSegment.NONE

        if on_track and self._phase is not _Phase.DRIVE:
            # found again, however far into the scan this was -- stop and resume right there
            self._phase = _Phase.DRIVE
            return True, None, False

        if self._phase is _Phase.DRIVE:
            if on_track:
                return True, None, False
            # just lost the line -- halt (drive_straight goes False) and kick off the scan
            return (False, *self._start_scan())

        if self._phase is _Phase.LOOK_STRAIGHT:
            self._phase_ticks_left -= 1
            if self._phase_ticks_left > 0:
                return False, None, False
            self._phase = _Phase.LOOK_SMALL_LEFT
            return False, TurnCommand(-self._small_scan_degrees), False

        if self._phase is _Phase.LOOK_SMALL_LEFT:
            if not motor_done:
                return False, None, False
            self._phase = _Phase.LOOK_SMALL_RIGHT
            # sweep from -small_scan_degrees to +small_scan_degrees
            return False, TurnCommand(2 * self._small_scan_degrees), False

        if self._phase is _Phase.LOOK_SMALL_RIGHT:
            if not motor_done:
                return False, None, False
            self._phase = _Phase.LOOK_LEFT
            # currently at +small_scan_degrees -- sweep on out to the full -scan_degrees
            return False, TurnCommand(-(self._scan_degrees + self._small_scan_degrees)), False

        if self._phase is _Phase.LOOK_LEFT:
            if not motor_done:
                return False, None, False
            self._phase = _Phase.LOOK_RIGHT
            return False, TurnCommand(2 * self._scan_degrees), False  # sweep from -scan_degrees to +scan_degrees

        # LOOK_RIGHT
        if not motor_done:
            return False, None, False
        self.reset()
        return False, None, True

    def _start_scan(self) -> tuple[TurnCommand | None, bool]:
        self._phase = _Phase.LOOK_STRAIGHT
        self._phase_ticks_left = self._look_straight_ticks
        return None, False

    def reset(self) -> None:
        """Forces back to driving straight, e.g. on a mode switch or after giving up — the next
        update() simply halts and starts a fresh scan the instant the line isn't seen.
        """
        self._phase = _Phase.DRIVE


class DriveDirection(Enum):
    NONE = auto()
    FORWARD = auto()
    BACKWARD = auto()


class DriveToggle:
    """Press-once accelerator/reverse toggle: forward starts driving until pressed again;
    backward switches directly from any state (and vice versa). Used by line-follower mode only —
    free-drive uses held_to_forward() below instead, since holding the button down is expected
    there.
    """

    def __init__(self) -> None:
        self._direction = DriveDirection.NONE

    @property
    def direction(self) -> DriveDirection:
        return self._direction

    def update(self, forward_pressed: bool, backward_pressed: bool) -> DriveDirection:
        """Call once per tick with this tick's edge-triggered forward/backward button presses."""
        if forward_pressed:
            self._direction = DriveDirection.NONE if self._direction is DriveDirection.FORWARD else DriveDirection.FORWARD
        elif backward_pressed:
            self._direction = DriveDirection.NONE if self._direction is DriveDirection.BACKWARD else DriveDirection.BACKWARD
        return self._direction

    def stop(self) -> None:
        """Forces the direction back to NONE, e.g. on a mode switch or after giving up a line search."""
        self._direction = DriveDirection.NONE


def direction_to_forward(direction: DriveDirection) -> float:
    """Maps a DriveToggle direction to a plain forward/none signal: 1.0, -1.0, or 0.0."""
    if direction is DriveDirection.FORWARD:
        return 1.0
    if direction is DriveDirection.BACKWARD:
        return -1.0
    return 0.0


def held_to_forward(forward_held: bool, backward_held: bool) -> float:
    """Maps free-drive's hold-to-drive accelerator/reverse buttons directly to the forward value
    arcade_drive expects, without any latching state — releasing the button stops the car.
    """
    if forward_held:
        return 1.0
    if backward_held:
        return -1.0
    return 0.0
