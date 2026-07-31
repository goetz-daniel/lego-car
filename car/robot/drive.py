"""Pure drive math: turns gamepad input into independent left/right motor speeds. No hardware/IO here."""

from collections import deque
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
    """A relative, in-place pivot: positive degrees turns right, negative turns left.

    is_scan marks the look-left/look-right sweep turns, where the sensor must actually catch the
    line mid-turn -- these are driven much slower than a blind align/recovery-straighten pivot,
    which needs no sensor reading and so can turn at normal speed.
    """

    degrees: float
    is_scan: bool = False


@dataclass(frozen=True)
class MoveCommand:
    """A straight drive for a set number of wheel-rotation degrees: positive forward, negative backward."""

    degrees: float


MotorCommand = TurnCommand | MoveCommand


class _Phase(Enum):
    LOOK_STRAIGHT = auto()
    LOOK_LEFT = auto()
    LOOK_RIGHT = auto()
    ALIGN = auto()
    STEP = auto()
    RECOVER_BACK = auto()


_RECENT_STEPS_TO_RETRACE = 2


class LineStepper:
    """Discrete 'halt, scan, decide, align, step forward' line following for a single
    downward-facing color sensor — the car translates only during a step, never while scanning.
    Every turn/step is an exact, IMU-verified command (LEGO's movement_turn_for_degrees()/
    movement_move_for_degrees()) rather than an approximated "hold some motor power for a few
    ticks" guess, so it's accurate regardless of speed or surface friction.

    Each cycle it comes to a translational halt and pivots through three brief looks — dead
    ahead (a short dwell, no movement needed), then left, then right (look_degrees off of
    straight ahead) — reading the sensor throughout. Whichever direction (if any) saw the line
    becomes this cycle's found position; the car then pivots back to face exactly that position
    (ALIGN, skipped if it's already facing it) before driving straight forward for a step (STEP)
    — never second-guessed mid-step, since it's already aimed exactly where the line was last
    confirmed.

    Every step is the same fixed, cautious step_degrees, whether the found position was dead
    ahead or a curve, and regardless of track segment — small enough to re-check often on a
    sharp curve, and never so large it can carry the car outside the line on a straight run
    either. The only thing that differs on a curve at all is inherent to aligning off-center: the
    ALIGN swing to face a found left/right position is naturally bigger than the (zero-length,
    skipped) swing for a dead-ahead find — no separate curve/straight bookkeeping is needed for
    that. The green BOOST segment is guaranteed straight for its whole length, so update() resets
    and returns no command — the caller drives straight through continuously at full speed
    instead, the one deliberate exception to "always the same step size".

    If a scan finds the line nowhere, this doesn't panic immediately: it first straightens back to
    center — undoing however this cycle's own look-left/look-right ended up pointed — then, if any
    steps have been taken yet, backs up exactly the distance covered by the last couple of them
    (retracing the path it just drove, since that's the last place the line was confirmed), and
    re-scans with a wider recovery_look_degrees — a tight curve entered too fast is often
    recoverable this way. Only if that broader re-scan also finds nothing does update() report
    gave_up, so the caller can stop, honk, and prompt for repositioning.
    """

    def __init__(
        self,
        look_degrees: float,
        look_straight_ticks: int,
        recovery_look_degrees: float,
        step_degrees: float,
    ) -> None:
        self._look_degrees = look_degrees
        self._look_straight_ticks = max(1, look_straight_ticks)
        self._recovery_look_degrees = recovery_look_degrees
        self._step_degrees = step_degrees

        self._recent_step_degrees: deque[float] = deque(maxlen=_RECENT_STEPS_TO_RETRACE)
        self._recovering = False
        self._next_step_degrees = 0.0
        self._retrace_degrees = 0.0
        self._after_align = _Phase.STEP

        self._scan_degrees = self._look_degrees
        self._phase = _Phase.LOOK_STRAIGHT
        self._phase_ticks_left = self._look_straight_ticks
        self._found_straight = False
        self._found_left = False
        self._found_right = False

    @property
    def is_searching(self) -> bool:
        return self._recovering

    def update(self, segment: TrackSegment, motor_done: bool) -> tuple[MotorCommand | None, bool]:
        """Call once per tick with the freshly detected segment and whether the previously issued
        command (if any) has finished on the hub. Returns (command, gave_up): command is the new
        turn/move to issue this tick (non-blocking — poll motor_done next tick), or None if there's
        nothing new to send (still dwelling, or still waiting on the in-flight command). gave_up is
        whether the line has gone unfound for so long — even after trying to recover — that the
        car should stop and be repositioned.
        """
        if segment is TrackSegment.BOOST:
            self.reset()
            return None, False  # caller drives straight through continuously instead, see class docstring

        on_track = segment is not TrackSegment.NONE

        # each look direction only needs to remember WHETHER it saw the line, not which segment --
        # every found position takes the same fixed step regardless of segment
        if self._phase is _Phase.LOOK_STRAIGHT:
            if on_track:
                self._found_straight = True
            self._phase_ticks_left -= 1
            if self._phase_ticks_left > 0:
                return None, False
            self._phase = _Phase.LOOK_LEFT
            return TurnCommand(-self._scan_degrees, is_scan=True), False

        if self._phase is _Phase.LOOK_LEFT:
            if on_track:
                self._found_left = True
            if not motor_done:
                return None, False
            self._phase = _Phase.LOOK_RIGHT
            return TurnCommand(2 * self._scan_degrees, is_scan=True), False  # sweep from -scan_degrees to +scan_degrees

        if self._phase is _Phase.LOOK_RIGHT:
            if on_track:
                self._found_right = True
            if not motor_done:
                return None, False
            return self._decide()

        if self._phase is _Phase.ALIGN:
            if not motor_done:
                return None, False
            if self._after_align is _Phase.RECOVER_BACK:
                self._phase = _Phase.RECOVER_BACK
                return MoveCommand(-self._retrace_degrees), False
            if self._after_align is _Phase.LOOK_STRAIGHT:  # nothing to retrace -- straight to the wider re-scan
                return self._start_scan(self._recovery_look_degrees)
            self._phase = _Phase.STEP
            return MoveCommand(self._next_step_degrees), False

        if self._phase is _Phase.STEP:
            if not motor_done:
                return None, False
            self._recent_step_degrees.append(self._next_step_degrees)
            return self._start_scan(self._look_degrees)

        # RECOVER_BACK
        if not motor_done:
            return None, False
        return self._start_scan(self._recovery_look_degrees)

    def _decide(self) -> tuple[MotorCommand | None, bool]:
        """Ends a look-straight/left/right scan: picks the found position (if any), and starts
        aligning to it for a fixed-size step — or starts recovering/gives up on a miss.
        """
        if self._found_straight:
            position = 0.0
        elif self._found_left and not self._found_right:
            position = -self._scan_degrees
        elif self._found_right and not self._found_left:
            position = self._scan_degrees
        elif self._found_left or self._found_right:  # both sides -- ambiguous, treat as centered
            position = 0.0
        else:
            position = None
        self._found_straight = self._found_left = self._found_right = False

        if position is None:
            return self._recover_or_give_up()

        self._recovering = False
        return self._start_align_then_step(position, self._step_degrees)

    def _recover_or_give_up(self) -> tuple[MotorCommand | None, bool]:
        """A scan found the line nowhere. First attempt: straighten out, back up along the last
        couple of steps (if any), and re-scan wider. Second consecutive miss (that recovery
        attempt also failed): give up.
        """
        if self._recovering:
            self.reset()
            return None, True

        self._recovering = True
        self._retrace_degrees = sum(self._recent_step_degrees)
        # those steps are now either retraced or irrelevant -- don't let them pollute a *future* retrace
        self._recent_step_degrees.clear()
        self._after_align = _Phase.RECOVER_BACK if self._retrace_degrees > 0 else _Phase.LOOK_STRAIGHT
        self._phase = _Phase.ALIGN
        # currently facing +scan_degrees (right), from having just finished LOOK_RIGHT -- straighten to center
        return TurnCommand(-self._scan_degrees), False

    def _start_align_then_step(self, position: float, step_degrees: float) -> tuple[MotorCommand | None, bool]:
        self._next_step_degrees = step_degrees
        # currently facing +scan_degrees (right); the signed turn needed to reach position from there
        align_degrees = position - self._scan_degrees
        if align_degrees == 0.0:  # already facing right, where the line was found
            self._phase = _Phase.STEP
            return MoveCommand(step_degrees), False
        self._after_align = _Phase.STEP
        self._phase = _Phase.ALIGN
        return TurnCommand(align_degrees), False

    def _start_scan(self, scan_degrees: float) -> tuple[MotorCommand | None, bool]:
        self._scan_degrees = scan_degrees
        self._found_straight = self._found_left = self._found_right = False
        self._phase = _Phase.LOOK_STRAIGHT
        self._phase_ticks_left = self._look_straight_ticks
        return None, False

    def reset(self) -> None:
        """Forces back to the start of a fresh straight-ahead scan at the normal look angle, e.g.
        on a mode switch, a boost segment, or after giving up.
        """
        self._recent_step_degrees.clear()
        self._recovering = False
        self._start_scan(self._look_degrees)


class DriveDirection(Enum):
    NONE = auto()
    FORWARD = auto()
    BACKWARD = auto()


class DriveToggle:
    """Turns a press-once accelerator/reverse button pair into indefinite driving, instead of
    needing to hold a button down the whole time.

    Pressing forward starts driving forward until forward is pressed again (which stops it);
    pressing backward switches directly to backward from any state (and vice versa), so reversing
    out of a forward drive does not require stopping first. Used by line-follower mode only —
    free-drive mode drives directly off held_to_forward() below instead, since holding a manual
    drive button down is expected there and locking it on with a single press would be surprising.
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
    """Maps a DriveToggle direction to the forward value arcade_drive/line_follow_drive expect."""
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
