import random

from car.robot.drive import (
    _REDIRECT_CLEAR_TICKS,
    AdventureDriver,
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


# ── AdventureDriver ────────────────────────────────────────────────────────────

_ADV_TICKS = 5


def _new_driver(ticks: int = _ADV_TICKS) -> AdventureDriver:
    return AdventureDriver(ticks, ticks, rng=random.Random(42))


def test_adventure_driver_starts_with_continuous_drive():
    driver = _new_driver()
    continuous, command, _ = driver.update(on_red=False, motor_done=True)
    assert continuous is True
    assert command is None
    assert not driver.is_redirecting


def test_adventure_driver_drives_forward_while_ticks_remain():
    driver = _new_driver(ticks=20)
    for _ in range(10):  # well within 20 ticks
        continuous, command, _ = driver.update(on_red=False, motor_done=True)
        assert continuous is True
        assert command is None


def test_adventure_driver_on_red_returns_a_turn_command():
    driver = _new_driver()
    continuous, command, _ = driver.update(on_red=True, motor_done=True)
    assert continuous is False
    assert isinstance(command, TurnCommand)
    assert driver.is_redirecting


def test_adventure_driver_redirect_is_exactly_180_degrees():
    driver = _new_driver()
    _, command, _ = driver.update(on_red=True, motor_done=True)
    assert command is not None
    assert abs(command.degrees) == 180.0


def test_adventure_driver_ignores_further_red_while_redirecting():
    driver = _new_driver()
    driver.update(on_red=True, motor_done=True)  # start redirect
    continuous, command, _ = driver.update(on_red=True, motor_done=False)
    assert continuous is False
    assert command is None  # no new command -- still waiting for the original turn


def test_adventure_driver_waits_for_motor_done_during_redirect():
    driver = _new_driver()
    driver.update(on_red=True, motor_done=True)  # start redirect
    assert driver.update(on_red=False, motor_done=False) == (False, None, False)  # still turning


def test_adventure_driver_resumes_driving_after_redirect_completes():
    driver = _new_driver()
    driver.update(on_red=True, motor_done=True)  # start redirect
    driver.update(on_red=False, motor_done=False)  # turning...
    continuous, command, _ = driver.update(on_red=False, motor_done=True)  # done
    assert continuous is True
    assert command is None
    assert not driver.is_redirecting


def test_adventure_driver_lost_if_on_red_after_redirect():
    # redirect completes → enters clearing phase (drive forward to get off the line)
    driver = _new_driver()
    driver.update(on_red=True, motor_done=True)  # start redirect
    driver.update(on_red=False, motor_done=False)  # turning...
    continuous, command, lost = driver.update(on_red=False, motor_done=True)  # redirect done → clearing
    assert continuous is True and command is None and lost is False  # NOT lost yet; now in clearing


def test_adventure_driver_clearing_drives_through_red():
    driver = _new_driver()
    driver.update(on_red=True, motor_done=True)  # start redirect
    driver.update(on_red=False, motor_done=False)  # turning...
    driver.update(on_red=False, motor_done=True)  # redirect done → clearing starts
    for _ in range(_REDIRECT_CLEAR_TICKS - 1):
        continuous, command, lost = driver.update(on_red=True, motor_done=True)
        assert continuous is True and command is None and lost is False  # ignores red during clearing


def test_adventure_driver_lost_after_clearing_still_on_red():
    driver = _new_driver()
    driver.update(on_red=True, motor_done=True)
    driver.update(on_red=False, motor_done=False)
    driver.update(on_red=False, motor_done=True)  # → clearing
    for _ in range(_REDIRECT_CLEAR_TICKS - 1):
        driver.update(on_red=True, motor_done=True)  # clearing ticks pass
    continuous, command, lost = driver.update(on_red=True, motor_done=True)  # clearing expires on red
    assert lost is True and continuous is False and command is None
    assert not driver.is_redirecting


def test_adventure_driver_clears_successfully_when_off_red():
    driver = _new_driver()
    driver.update(on_red=True, motor_done=True)
    driver.update(on_red=False, motor_done=False)
    driver.update(on_red=False, motor_done=True)  # → clearing
    for _ in range(_REDIRECT_CLEAR_TICKS - 1):
        driver.update(on_red=False, motor_done=True)
    continuous, command, lost = driver.update(on_red=False, motor_done=True)  # clearing expires, clear
    assert lost is False and continuous is True and command is None


def test_adventure_driver_eventually_issues_a_voluntary_turn():
    # ticks=1 so the drive phase expires every tick; 50 iterations easily covers the 40% turn chance
    driver = _new_driver(ticks=1)
    for _ in range(50):
        continuous, command, _ = driver.update(on_red=False, motor_done=True)
        if command is not None:
            assert isinstance(command, TurnCommand)
            assert not driver.is_redirecting
            return
    raise AssertionError("Expected a voluntary TurnCommand within 50 ticks")


def test_adventure_driver_waits_for_motor_done_after_voluntary_turn():
    driver = _new_driver(ticks=1)
    command = None
    for _ in range(50):
        _, command, _ = driver.update(on_red=False, motor_done=True)
        if command is not None:
            break
    assert command is not None
    assert driver.update(on_red=False, motor_done=False) == (False, None, False)  # still turning
    continuous, cmd, _ = driver.update(on_red=False, motor_done=True)  # done
    assert continuous is True
    assert cmd is None


def test_adventure_driver_reset_returns_to_drive_state():
    driver = _new_driver()
    driver.update(on_red=True, motor_done=True)  # start redirect
    assert driver.is_redirecting
    driver.reset()
    assert not driver.is_redirecting
    continuous, command, _ = driver.update(on_red=False, motor_done=True)
    assert continuous is True
    assert command is None


def test_adventure_driver_voluntary_turn_within_range():
    driver = _new_driver(ticks=1)
    for _ in range(100):
        _, command, _ = driver.update(on_red=False, motor_done=True)
        if command is not None:
            assert not driver.is_boosting
            assert abs(command.degrees) <= 180.0
