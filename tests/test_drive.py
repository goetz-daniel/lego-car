from car.robot.drive import (
    DriveDirection,
    DriveToggle,
    LineFollower,
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


_SMALL_SCAN_DEGREES = 15.0
_SCAN_DEGREES = 90.0
_LOOK_STRAIGHT_TICKS = 2


def _new_follower() -> LineFollower:
    return LineFollower(_SMALL_SCAN_DEGREES, _SCAN_DEGREES, _LOOK_STRAIGHT_TICKS)


def test_line_follower_drives_straight_continuously_while_on_track():
    follower = _new_follower()
    assert follower.update(TrackSegment.NORMAL, True) == (True, None, False)
    assert follower.update(TrackSegment.BOOST, True) == (True, None, False)
    assert not follower.is_searching


def test_line_follower_losing_the_line_halts_and_starts_a_scan():
    follower = _new_follower()
    assert follower.update(TrackSegment.NONE, True) == (False, None, False)
    assert follower.is_searching
    assert follower._phase.name == "LOOK_STRAIGHT"


def test_line_follower_look_straight_dwells_before_sweeping_the_small_scan():
    follower = _new_follower()
    follower.update(TrackSegment.NONE, True)  # halts -- starts the dwell
    assert follower.update(TrackSegment.NONE, True) == (False, None, False)  # still dwelling dead-ahead
    assert follower.update(TrackSegment.NONE, True) == (False, TurnCommand(-_SMALL_SCAN_DEGREES), False)
    assert follower._phase.name == "LOOK_SMALL_LEFT"
    # sweeps from -small_scan_degrees all the way to +small_scan_degrees in one turn
    assert follower.update(TrackSegment.NONE, True) == (False, TurnCommand(2 * _SMALL_SCAN_DEGREES), False)
    assert follower._phase.name == "LOOK_SMALL_RIGHT"


def test_line_follower_waits_for_motor_done_before_advancing_past_a_turn():
    follower = _new_follower()
    follower.update(TrackSegment.NONE, True)
    follower.update(TrackSegment.NONE, True)
    follower.update(TrackSegment.NONE, True)  # small-look-left turn issued
    assert follower.update(TrackSegment.NONE, False) == (False, None, False)  # still turning -- nothing new to send
    assert follower._phase.name == "LOOK_SMALL_LEFT"  # hasn't advanced yet
    assert follower.update(TrackSegment.NONE, True) == (False, TurnCommand(2 * _SMALL_SCAN_DEGREES), False)  # now advances


def test_line_follower_found_mid_turn_stops_scanning_and_resumes_driving():
    follower = _new_follower()
    follower.update(TrackSegment.NONE, True)
    follower.update(TrackSegment.NONE, True)
    follower.update(TrackSegment.NONE, True)  # small-look-left turn issued, now mid-sweep
    # found the line while the sweep is still in flight (motor_done False) -- doesn't matter, stop
    # right there and resume driving immediately
    assert follower.update(TrackSegment.NORMAL, False) == (True, None, False)
    assert not follower.is_searching


def _scan_through_to_wide_right(follower: LineFollower) -> None:
    """Drives a follower through the entire small-scan-then-wide-scan sequence finding nothing,
    ending exactly on the tick the wide right sweep is issued (the next update() decides give-up).
    """
    follower.update(TrackSegment.NONE, True)  # halt -- start dwell
    follower.update(TrackSegment.NONE, True)  # still dwelling
    follower.update(TrackSegment.NONE, True)  # small-look-left issued
    follower.update(TrackSegment.NONE, True)  # small-look-right issued
    follower.update(TrackSegment.NONE, True)  # wide look-left issued
    follower.update(TrackSegment.NONE, True)  # wide look-right issued


def test_line_follower_small_scan_failure_continues_into_the_wide_scan():
    follower = _new_follower()
    follower.update(TrackSegment.NONE, True)
    follower.update(TrackSegment.NONE, True)
    follower.update(TrackSegment.NONE, True)  # small-look-left issued
    follower.update(TrackSegment.NONE, True)  # small-look-right issued
    # small scan found nothing -- continues straight into the wider fallback sweep
    assert follower.update(TrackSegment.NONE, True) == (False, TurnCommand(-(_SCAN_DEGREES + _SMALL_SCAN_DEGREES)), False)
    assert follower._phase.name == "LOOK_LEFT"
    assert follower.update(TrackSegment.NONE, True) == (False, TurnCommand(2 * _SCAN_DEGREES), False)
    assert follower._phase.name == "LOOK_RIGHT"


def test_line_follower_wide_scan_failure_gives_up():
    follower = _new_follower()
    _scan_through_to_wide_right(follower)
    assert follower.update(TrackSegment.NONE, True) == (False, None, True)  # nothing found at all -- gives up
    assert not follower.is_searching
    assert follower._phase.name == "DRIVE"


def test_line_follower_found_during_the_wide_scan_resumes_driving():
    follower = _new_follower()
    follower.update(TrackSegment.NONE, True)
    follower.update(TrackSegment.NONE, True)
    follower.update(TrackSegment.NONE, True)  # small-look-left issued
    follower.update(TrackSegment.NONE, True)  # small-look-right issued
    follower.update(TrackSegment.NONE, True)  # wide look-left issued, now mid-sweep
    assert follower.update(TrackSegment.NORMAL, False) == (True, None, False)
    assert not follower.is_searching


def test_line_follower_reset_forces_back_to_driving():
    follower = _new_follower()
    follower.update(TrackSegment.NONE, True)
    follower.update(TrackSegment.NONE, True)  # now mid-scan
    follower.reset()
    assert not follower.is_searching
    assert follower._phase.name == "DRIVE"
    assert follower.update(TrackSegment.NORMAL, True) == (True, None, False)


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
