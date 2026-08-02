"""Pure drive math: turns gamepad input into independent left/right motor speeds. No hardware/IO here."""

import random as _random
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
    backward switches directly from any state (and vice versa). Used by line-follower and adventure
    modes — free-drive uses held_to_forward() below instead, since holding the button down is
    expected there.
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


_WIGGLE_FLIP_TICKS = 8  # half-period of wiggle direction change (ticks per direction)
_REDIRECT_CLEAR_TICKS = 8  # ticks to drive forward after U-turn before declaring lost
_STYLE_WEIGHTS = (3, 2, 2, 1)  # straight, wiggle, curve, circle — straight most common, circle rare


class _AdventurePhase(Enum):
    DRIVE = auto()
    TURNING = auto()
    REDIRECTING = auto()
    CLEARING = auto()  # brief forward drive after redirect to get off the red line


class AdventureDriver:
    """Autonomous arena wanderer: drives freely inside a red-bordered area.

    Each drive segment is one of four styles — straight, wiggle (left-right oscillation),
    curve (arc in one direction), or circle (tight full-steer arc) — never the same style twice in
    a row. On red: pivots 180° then drives forward briefly before resuming, to avoid false-positive
    lost detection.
    """

    def __init__(
        self,
        drive_ticks_min: int,
        drive_ticks_max: int,
        rng: _random.Random | None = None,
    ) -> None:
        self._drive_ticks_min = drive_ticks_min
        self._drive_ticks_max = drive_ticks_max
        self._rng = rng if rng is not None else _random.Random()
        self._phase = _AdventurePhase.DRIVE
        self._ticks_left = 0
        self._is_boosting = False
        self._steer = 0.0
        self._wiggle_flip_remaining = 0
        self._last_style = -1
        self._start_drive()

    @property
    def is_boosting(self) -> bool:
        return self._is_boosting

    @property
    def steer(self) -> float:
        """Steering bias for this drive segment: -1.0 = hard left, 0.0 = straight, 1.0 = hard right."""
        return self._steer

    @property
    def is_redirecting(self) -> bool:
        return self._phase is _AdventurePhase.REDIRECTING

    def reset(self) -> None:
        """Resets to the same state as newly constructed — next update() drives forward."""
        self._last_style = -1
        self._start_drive()

    def _start_drive(self) -> None:
        self._phase = _AdventurePhase.DRIVE
        self._wiggle_flip_remaining = 0
        styles = [s for s in (0, 1, 2, 3) if s != self._last_style]
        style = self._rng.choices(styles, weights=[_STYLE_WEIGHTS[s] for s in styles], k=1)[0]
        self._last_style = style
        if style == 0:  # straight
            self._steer = 0.0
            self._is_boosting = False
            self._ticks_left = self._rng.randint(self._drive_ticks_min, self._drive_ticks_max + self._drive_ticks_min)
        elif style == 1:  # wiggle: small left-right oscillation while going forward
            self._steer = 0.25 * self._rng.choice((-1, 1))
            self._is_boosting = False
            self._wiggle_flip_remaining = _WIGGLE_FLIP_TICKS
            self._ticks_left = self._rng.randint(self._drive_ticks_min * 2, self._drive_ticks_max + self._drive_ticks_min)
        elif style == 2:  # curve: consistent arc in one direction
            self._steer = self._rng.uniform(0.4, 0.7) * self._rng.choice((-1, 1))
            self._is_boosting = False
            self._ticks_left = self._rng.randint(self._drive_ticks_min, self._drive_ticks_max)
        else:  # circle: tight full-steer arc at boost speed
            self._steer = float(self._rng.choice((-1, 1)))
            self._is_boosting = True
            self._ticks_left = self._rng.randint(self._drive_ticks_min, self._drive_ticks_min + 10)

    def _random_turn(self) -> TurnCommand:
        degrees = self._rng.uniform(30.0, 180.0)
        self._is_boosting = False
        return TurnCommand(degrees * self._rng.choice((-1, 1)))

    def _redirect(self) -> TurnCommand:
        return TurnCommand(180.0 * self._rng.choice((-1, 1)))

    def update(self, on_red: bool, motor_done: bool) -> tuple[bool, TurnCommand | None, bool]:
        """Call once per tick. Returns (continuous_drive, command, lost): continuous_drive means call
        motors.drive() this tick; command is a new TurnCommand to dispatch once; lost means the
        post-redirect clearing drive ended while still on red — the car needs manual repositioning.
        """
        if self._phase is _AdventurePhase.CLEARING:
            self._ticks_left -= 1
            if self._ticks_left <= 0:
                if on_red:  # drove forward after U-turn, still on red = truly outside
                    return False, None, True
                self._start_drive()
            return True, None, False

        if self._phase is _AdventurePhase.REDIRECTING:
            if motor_done:
                self._phase = _AdventurePhase.CLEARING
                self._ticks_left = _REDIRECT_CLEAR_TICKS
                self._steer = 0.0
                self._is_boosting = False
                return True, None, False
            return False, None, False

        if self._phase is _AdventurePhase.TURNING:
            if motor_done:
                self._start_drive()
                return True, None, False
            return False, None, False

        # on_red only checked in DRIVE phase — never while a turn_for_degrees() is already in flight,
        # since issuing a second command before the first resolves leaves an orphaned pending future
        # in the LEGO library, causing done() to permanently return False and hanging the car.
        if on_red:
            self._phase = _AdventurePhase.REDIRECTING
            self._is_boosting = False
            return False, self._redirect(), False

        # DRIVE phase: handle wiggle oscillation, then count down ticks
        if self._wiggle_flip_remaining > 0:
            self._wiggle_flip_remaining -= 1
            if self._wiggle_flip_remaining == 0:
                self._steer = -self._steer
                self._wiggle_flip_remaining = _WIGGLE_FLIP_TICKS

        self._ticks_left -= 1
        if self._ticks_left <= 0:
            if self._rng.random() < 0.5:
                self._start_drive()
                return True, None, False
            self._phase = _AdventurePhase.TURNING
            return False, self._random_turn(), False

        return True, None, False
