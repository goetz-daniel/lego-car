from car.robot.drive import (
    DriveDirection,
    DriveToggle,
    LineStepper,
    MoveCommand,
    TurnCommand,
    analog_amount,
    arcade_drive,
    clamp,
    direction_to_forward,
    held_to_forward,
    throttle_for_boost,
)
from car.robot.track import TrackSegment


def test_clamp_bounds_value():
    assert clamp(5, 0, 10) == 5
    assert clamp(-5, 0, 10) == 0
    assert clamp(15, 0, 10) == 10


def test_throttle_for_boost_picks_base_or_max():
    assert throttle_for_boost(boost_amount=0.0, base_speed_percent=50, max_speed_percent=100) == 0.5
    assert throttle_for_boost(boost_amount=1.0, base_speed_percent=50, max_speed_percent=100) == 1.0


def test_throttle_for_boost_interpolates_partial_amounts():
    assert throttle_for_boost(boost_amount=0.5, base_speed_percent=50, max_speed_percent=100) == 0.75


def test_analog_amount_normalizes_rest_to_peak_range():
    assert analog_amount(raw_value=-1.0, rest=-1.0, peak=1.0) == 0.0
    assert analog_amount(raw_value=1.0, rest=-1.0, peak=1.0) == 1.0
    assert analog_amount(raw_value=0.0, rest=-1.0, peak=1.0) == 0.5


def test_analog_amount_clamps_outside_the_calibrated_range():
    assert analog_amount(raw_value=2.0, rest=-1.0, peak=1.0) == 1.0
    assert analog_amount(raw_value=-2.0, rest=-1.0, peak=1.0) == 0.0


def test_arcade_drive_straight_drives_both_wheels_equally():
    left, right = arcade_drive(forward=1.0, turn=0.0, throttle=1.0, turn_scale=0.5)
    assert left == right == 100


def test_arcade_drive_turn_speeds_up_one_wheel_and_slows_the_other():
    left, right = arcade_drive(forward=1.0, turn=1.0, throttle=1.0, turn_scale=0.5)
    assert left == 100
    assert right == 50


def test_arcade_drive_clamps_instead_of_exceeding_max_speed():
    left, right = arcade_drive(forward=1.0, turn=1.0, throttle=1.0, turn_scale=1.0)
    assert left == 100
    assert right == 0


_LOOK_DEGREES = 72.0
_RECOVERY_LOOK_DEGREES = 180.0
_LOOK_STRAIGHT_TICKS = 2
_STEP = 90.0


def _new_stepper() -> LineStepper:
    return LineStepper(_LOOK_DEGREES, _LOOK_STRAIGHT_TICKS, _RECOVERY_LOOK_DEGREES, _STEP)


def _on_track_for_phase(stepper: LineStepper, line_offset: float) -> bool:
    """Simulates whether the line is under the sensor given the car's current scan heading."""
    phase = stepper._phase.name
    scan = stepper._scan_degrees
    if phase == "LOOK_STRAIGHT":
        return line_offset == 0.0
    if phase == "LOOK_LEFT":
        return line_offset == -scan
    if phase == "LOOK_RIGHT":
        return line_offset == scan
    return False  # ALIGN/STEP/RECOVER_BACK never read the sensor for decisions


def _tick(stepper: LineStepper, line_offset: float, segment: TrackSegment = TrackSegment.NORMAL, motor_done: bool = True):
    """Simulates one tick, always reporting the in-flight command (if any) as finished by default --
    real hardware naturally takes an arbitrary, uninteresting-to-test number of ticks to report
    done, so tests only need to simulate the "still busy" case explicitly where it matters.
    """
    on_track = _on_track_for_phase(stepper, line_offset)
    return stepper.update(segment if on_track else TrackSegment.NONE, motor_done)


def _run_full_cycle(stepper: LineStepper, line_offset: float, segment: TrackSegment = TrackSegment.NORMAL, max_ticks: int = 10):
    """Feeds ticks (simulating the line at line_offset, e.g. 0.0=straight, -look_degrees=left curve,
    or a value matching no scan angle=missed) until a full scan+align+step (or scan+recovery)
    cycle resolves back to a fresh halted scan, or the stepper gives up.
    """
    results = []
    for _ in range(max_ticks):
        phase_before = stepper._phase.name
        result = _tick(stepper, line_offset, segment)
        results.append(result)
        if result[1] or (phase_before != "LOOK_STRAIGHT" and stepper._phase.name == "LOOK_STRAIGHT"):
            break
    return results


def test_line_stepper_scan_issues_turn_commands_for_left_then_right_while_halted():
    stepper = _new_stepper()
    r1 = stepper.update(TrackSegment.NONE, True)
    r2 = stepper.update(TrackSegment.NONE, True)
    r3 = stepper.update(TrackSegment.NONE, True)
    r4 = stepper.update(TrackSegment.NONE, True)
    assert r1 == (None, False)  # first look-straight tick -- still dwelling
    assert r2 == (TurnCommand(-_LOOK_DEGREES, is_scan=True), False)  # look-straight done -- pivot to look-left
    assert r3 == (TurnCommand(2 * _LOOK_DEGREES, is_scan=True), False)  # look-left done -- sweep to look-right
    assert r4 == (TurnCommand(-_LOOK_DEGREES), False)  # nothing found -- recovery straightens back to center


def test_line_stepper_waits_for_motor_done_before_advancing_past_a_turn():
    stepper = _new_stepper()
    stepper.update(TrackSegment.NONE, True)
    issued = stepper.update(TrackSegment.NONE, True)  # look-straight done -- issues the look-left turn
    assert issued == (TurnCommand(-_LOOK_DEGREES, is_scan=True), False)
    still_turning = stepper.update(TrackSegment.NONE, False)  # hub hasn't finished the turn yet
    assert still_turning == (None, False)
    assert stepper._phase.name == "LOOK_LEFT"  # no phase advance while busy
    now_done = stepper.update(TrackSegment.NONE, True)
    assert now_done == (TurnCommand(2 * _LOOK_DEGREES, is_scan=True), False)  # resumes once the hub reports done


def test_line_stepper_first_straight_find_takes_a_short_step_and_aligns_back_to_center():
    stepper = _new_stepper()
    r1 = stepper.update(TrackSegment.NORMAL, True)  # look-straight tick 1 -- found dead ahead
    r2 = stepper.update(TrackSegment.NORMAL, True)  # look-straight tick 2 -- pivot to look-left
    r3 = stepper.update(TrackSegment.NONE, True)  # look-left -- not found -- sweep to look-right
    r4 = stepper.update(TrackSegment.NONE, True)  # look-right -- not found -- decide: found dead ahead
    r5 = stepper.update(TrackSegment.NONE, True)  # align finishes -- step forward
    r6 = stepper.update(TrackSegment.NONE, True)  # step finishes -- fresh halted scan
    assert r1 == (None, False)
    assert r2 == (TurnCommand(-_LOOK_DEGREES, is_scan=True), False)
    assert r3 == (TurnCommand(2 * _LOOK_DEGREES, is_scan=True), False)
    assert r4 == (TurnCommand(-_LOOK_DEGREES), False)  # aligns back to center
    assert r5 == (MoveCommand(_STEP), False)  # every step is this same fixed size
    assert r6 == (None, False)


def test_line_stepper_two_consecutive_straight_finds_take_the_same_fixed_step():
    stepper = _new_stepper()
    cycle1 = _run_full_cycle(stepper, line_offset=0.0)
    assert [r[0] for r in cycle1 if isinstance(r[0], MoveCommand)] == [MoveCommand(_STEP)]
    cycle2 = _run_full_cycle(stepper, line_offset=0.0)
    assert [r[0] for r in cycle2 if isinstance(r[0], MoveCommand)] == [MoveCommand(_STEP)]


def test_line_stepper_curve_found_right_skips_align_and_steps_directly():
    stepper = _new_stepper()
    stepper.update(TrackSegment.NONE, True)
    stepper.update(TrackSegment.NONE, True)
    stepper.update(TrackSegment.NONE, True)  # -> look-right
    decide_result = stepper.update(TrackSegment.NORMAL, True)  # found to the right
    step_result = stepper.update(TrackSegment.NONE, True)
    assert decide_result == (MoveCommand(_STEP), False)  # already facing right -- no align needed
    assert step_result == (None, False)


def test_line_stepper_curve_found_left_needs_a_full_align_swing_before_stepping():
    stepper = _new_stepper()
    stepper.update(TrackSegment.NONE, True)
    stepper.update(TrackSegment.NONE, True)  # -> look-left
    stepper.update(TrackSegment.NORMAL, True)  # found to the left -- sweep on to look-right
    decide_result = stepper.update(TrackSegment.NONE, True)
    align_result = stepper.update(TrackSegment.NONE, True)
    step_result = stepper.update(TrackSegment.NONE, True)
    assert decide_result == (TurnCommand(-2 * _LOOK_DEGREES), False)  # full swing from +look to -look
    assert align_result == (MoveCommand(_STEP), False)
    assert step_result == (None, False)


def test_line_stepper_curve_then_straight_take_the_same_fixed_step():
    stepper = _new_stepper()
    cycle1 = _run_full_cycle(stepper, line_offset=-_LOOK_DEGREES)  # a curve
    cycle2 = _run_full_cycle(stepper, line_offset=0.0)  # straight right after a curve
    assert [r[0] for r in cycle1 if isinstance(r[0], MoveCommand)] == [MoveCommand(_STEP)]
    assert [r[0] for r in cycle2 if isinstance(r[0], MoveCommand)] == [MoveCommand(_STEP)]


def test_line_stepper_goal_segment_takes_the_same_fixed_step():
    stepper = _new_stepper()
    cycle1 = _run_full_cycle(stepper, line_offset=0.0, segment=TrackSegment.GOAL)
    cycle2 = _run_full_cycle(stepper, line_offset=0.0, segment=TrackSegment.GOAL)
    assert [r[0] for r in cycle1 if isinstance(r[0], MoveCommand)] == [MoveCommand(_STEP)]
    assert [r[0] for r in cycle2 if isinstance(r[0], MoveCommand)] == [MoveCommand(_STEP)]  # segment doesn't change it


def test_line_stepper_boost_segment_bypasses_scanning_and_returns_no_command():
    stepper = _new_stepper()
    results = [stepper.update(TrackSegment.BOOST, True) for _ in range(5)]
    assert all(r == (None, False) for r in results)
    assert not stepper.is_searching
    # boost resets the stepper, so the tick right after it ends is a fresh halted look-straight
    assert stepper.update(TrackSegment.NORMAL, True) == (None, False)


def test_line_stepper_miss_with_no_history_still_straightens_before_the_wider_rescan():
    stepper = _new_stepper()
    stepper.update(TrackSegment.NONE, True)
    stepper.update(TrackSegment.NONE, True)
    stepper.update(TrackSegment.NONE, True)
    decide_result = stepper.update(TrackSegment.NONE, True)  # nothing found -- recovery begins
    assert stepper.is_searching
    assert stepper._phase.name == "ALIGN"
    assert decide_result == (TurnCommand(-_LOOK_DEGREES), False)  # straightens out first, even with nothing to retrace
    rescan_result = stepper.update(TrackSegment.NONE, True)  # nothing to retrace -- straight to the wider re-scan
    assert rescan_result == (None, False)
    assert stepper._phase.name == "LOOK_STRAIGHT"
    assert stepper._scan_degrees == _RECOVERY_LOOK_DEGREES  # now re-scanning wider


def test_line_stepper_miss_with_history_retraces_the_last_steps_before_rescanning_wider():
    stepper = _new_stepper()
    _run_full_cycle(stepper, line_offset=0.0)  # step 1
    _run_full_cycle(stepper, line_offset=0.0)  # step 2 -- same fixed size as step 1
    expected_retrace_degrees = _STEP + _STEP

    never_found = 999.0
    for _ in range(3):
        _tick(stepper, never_found)
    align_result = _tick(stepper, never_found)  # decide: nothing found -- straighten first
    assert align_result == (TurnCommand(-_LOOK_DEGREES), False)
    recover_result = _tick(stepper, never_found)  # align done -- back up along the retraced steps
    assert recover_result == (MoveCommand(-expected_retrace_degrees), False)
    assert stepper._phase.name == "RECOVER_BACK"
    rescan_result = _tick(stepper, never_found)  # retrace done -- re-scan wider
    assert rescan_result == (None, False)
    assert stepper._phase.name == "LOOK_STRAIGHT"
    assert stepper._scan_degrees == _RECOVERY_LOOK_DEGREES
    assert stepper.is_searching


def test_line_stepper_recovery_clears_history_so_a_later_miss_only_retraces_the_resumed_step():
    stepper = _new_stepper()
    _run_full_cycle(stepper, line_offset=0.0)  # history=[step]
    _run_full_cycle(stepper, line_offset=0.0)  # history=[step, step]

    line_offset = 999.0  # miss the normal-width scan first
    for _ in range(20):
        phase_before = stepper._phase.name
        if phase_before == "RECOVER_BACK":
            line_offset = _RECOVERY_LOOK_DEGREES  # found already facing right -- skips align, straight to step
        _tick(stepper, line_offset)
        if phase_before == "LOOK_RIGHT" and stepper._phase.name != "LOOK_RIGHT" and not stepper.is_searching:
            break
    assert not stepper._recent_step_degrees  # the retraced steps are consumed, not carried forward
    assert stepper._phase.name == "STEP"

    _tick(stepper, 0.0)  # let the resumed step finish
    assert list(stepper._recent_step_degrees) == [_STEP]  # only the just-resumed step, no stale history

    never_found = 999.0  # a second miss right after resuming
    reversal = None
    for _ in range(20):
        phase_before = stepper._phase.name
        result = _tick(stepper, never_found)
        if phase_before == "ALIGN":
            reversal = result
            break
    assert reversal == (MoveCommand(-_STEP), False)  # retraces only the resumed step, not a stale double mix


def test_line_stepper_recovery_that_finds_the_line_resumes_with_the_same_fixed_step():
    stepper = _new_stepper()
    line_offset = 999.0  # miss the normal-width scan first (no step history yet -- skips RECOVER_BACK entirely)
    for _ in range(20):
        if stepper._scan_degrees == _RECOVERY_LOOK_DEGREES:
            line_offset = -_RECOVERY_LOOK_DEGREES  # findable only at the wider recovery angle
        result = _tick(stepper, line_offset)
        assert not result[1]  # never gives up -- the wider re-scan finds it
        if stepper._phase.name == "STEP" and not stepper.is_searching:
            break
    assert stepper._phase.name == "STEP"
    assert stepper._next_step_degrees == _STEP  # a resumed step is the same fixed size as any other


def test_line_stepper_recovery_failure_gives_up_and_resets():
    stepper = _new_stepper()
    _run_full_cycle(stepper, line_offset=0.0)
    never_found = 999.0
    gave_up = False
    for _ in range(30):
        _, gave_up_now = _tick(stepper, never_found)
        if gave_up_now:
            gave_up = True
            break
    assert gave_up
    assert not stepper.is_searching
    assert stepper._phase.name == "LOOK_STRAIGHT"
    assert not stepper._recent_step_degrees


def test_line_stepper_reset_forces_a_fresh_straight_look():
    stepper = _new_stepper()
    stepper.update(TrackSegment.NONE, True)  # partway into a look-straight
    stepper.update(TrackSegment.NONE, True)  # now into look-left
    stepper.reset()
    assert not stepper.is_searching
    assert stepper._phase.name == "LOOK_STRAIGHT"
    result = stepper.update(TrackSegment.NORMAL, True)
    assert result == (None, False)  # fresh look-straight, line found dead ahead


def test_direction_to_forward_maps_each_direction():
    assert direction_to_forward(DriveDirection.NONE) == 0.0
    assert direction_to_forward(DriveDirection.FORWARD) == 1.0
    assert direction_to_forward(DriveDirection.BACKWARD) == -1.0


def test_held_to_forward_maps_each_held_combination():
    assert held_to_forward(forward_held=False, backward_held=False) == 0.0
    assert held_to_forward(forward_held=True, backward_held=False) == 1.0
    assert held_to_forward(forward_held=False, backward_held=True) == -1.0


def test_held_to_forward_forward_wins_when_both_are_held():
    assert held_to_forward(forward_held=True, backward_held=True) == 1.0


def test_drive_toggle_starts_stopped():
    toggle = DriveToggle()
    assert toggle.direction is DriveDirection.NONE


def test_drive_toggle_forward_press_starts_and_stops_driving():
    toggle = DriveToggle()
    assert toggle.update(forward_pressed=True, backward_pressed=False) is DriveDirection.FORWARD
    assert toggle.update(forward_pressed=False, backward_pressed=False) is DriveDirection.FORWARD  # keeps driving
    assert toggle.update(forward_pressed=True, backward_pressed=False) is DriveDirection.NONE  # pressed again: stop


def test_drive_toggle_backward_press_while_driving_forward_switches_directly():
    toggle = DriveToggle()
    toggle.update(forward_pressed=True, backward_pressed=False)
    assert toggle.update(forward_pressed=False, backward_pressed=True) is DriveDirection.BACKWARD
    assert toggle.update(forward_pressed=True, backward_pressed=False) is DriveDirection.FORWARD


def test_drive_toggle_stop_forces_none():
    toggle = DriveToggle()
    toggle.update(forward_pressed=True, backward_pressed=False)
    toggle.stop()
    assert toggle.direction is DriveDirection.NONE
