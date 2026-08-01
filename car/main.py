"""Entry point: drive the Lego Education Car with a Bluetooth gamepad.

Run from the repository root (with the venv activated):
    python -m car.main
"""

import time
from collections.abc import Callable

import legoeducation as le

from car.cli import CARD_COLORS, get_connection_card
from car.controller.calibrate import run_calibration
from car.controller.gamepad import Gamepad
from car.robot.audio import AudioPlayer
from car.robot.boundary import BoundaryGuard
from car.robot.colorsensor import CarColorSensor
from car.robot.drive import (
    DriveDirection,
    DriveToggle,
    LineFollower,
    TurnCommand,
    arcade_drive,
    direction_to_forward,
    held_to_forward,
    throttle_for_boost,
)
from car.robot.motors import CarMotors
from car.robot.sound import CarSound
from car.robot.track import TrackSegment, TrackSegmentTracker, classify_track_segment
from car.robot.voice import VoiceLines
from car.settings import Settings, load as load_settings, save as save_settings
from car.ui import Dashboard, banner, console, error, success

_CONTROL_X: tuple[str, str] = ("X button", "Switch between free-drive and line-follower")
_CONTROL_Y: tuple[str, str] = ("Y button", "Play a random driver comment")
_CONTROL_EXIT: tuple[str, str] = ("Ctrl+C", "Stop and disconnect")
_FREE_DRIVE_CONTROLS: tuple[tuple[str, str], ...] = (
    ("A button", "Hold to drive forward"),
    ("B button", "Hold to drive backward"),
    _CONTROL_X,
    _CONTROL_Y,
    ("Turn stick/buttons", "Steer left/right"),
    ("Boost trigger/button", "Boost speed (hold)"),
    _CONTROL_EXIT,
)
_LINE_FOLLOWER_CONTROLS: tuple[tuple[str, str], ...] = (
    ("A button", "Press once to start, again to stop"),
    _CONTROL_X,
    _CONTROL_Y,
    _CONTROL_EXIT,
)


def _connect_gamepad(settings: Settings) -> Gamepad:
    """Connects to the gamepad, auto-calibrating and saving it if settings.json does not already recognize it."""
    with console.status("Connecting to gamepad..."):
        gamepad = Gamepad()
    success(f"Gamepad connected: {gamepad.name}")

    if settings.gamepad is None or settings.gamepad.name != gamepad.name:
        settings.gamepad = run_calibration(gamepad, settings)
        save_settings(settings)
        success("Gamepad calibrated and saved to settings.json.")
    gamepad.apply_calibration(settings.gamepad)
    return gamepad


def _connect_device(label: str, connect: Callable[[], bool]) -> bool:
    """Runs connect() with a status spinner, printing a consistent success/failure message."""
    with console.status(f"Connecting to {label}..."):
        connected = connect()
    if not connected:
        error(f"Could not connect to the {label}. Check that it is powered on and the card details are correct.")
        return False
    success(f"{label} connected.")
    return True


def _connect_motors(card_color: int, card_serial: str, settings: Settings) -> CarMotors | None:
    """Connects to the Double Motor, or returns None (after printing why) if that fails."""
    motors = CarMotors()
    connected = _connect_device(
        "Double Motor", lambda: motors.connect(card_color, card_serial, settings.drive_acceleration, settings.drive_deceleration)
    )
    return motors if connected else None


def _connect_colorsensor(card_color: int, card_serial: str) -> CarColorSensor | None:
    """Connects to the Color Sensor (mounted facing down at the front), or returns None if that fails."""
    colorsensor = CarColorSensor()
    connected = _connect_device("Color Sensor", lambda: colorsensor.connect(card_color, card_serial))
    return colorsensor if connected else None


def _set_light(motors: CarMotors, colorsensor: CarColorSensor, color: int, pattern: int = le.LIGHT_PATTERN_SOLID) -> None:
    """Mirrors the same status light on both the Double Motor and the Color Sensor."""
    motors.light(color, pattern)
    colorsensor.light(color, pattern)


def _set_light_on_change(
    motors: CarMotors,
    colorsensor: CarColorSensor,
    active: bool,
    was_active: bool,
    active_color: int,
    inactive_color: int,
    active_pattern: int = le.LIGHT_PATTERN_SOLID,
) -> bool:
    """Sets the status light only on the tick `active` actually flips, to `active_color`/
    `active_pattern` or plain `inactive_color`. Returns `active`, so callers can store it straight
    back as next tick's `was_active` — shared by every edge-triggered light toggle in the drive
    loop (searching, boosting in either mode), which otherwise all repeat this same shape.
    """
    if active != was_active:
        color = active_color if active else inactive_color
        pattern = active_pattern if active else le.LIGHT_PATTERN_SOLID
        _set_light(motors, colorsensor, color, pattern)
    return active


def _run_drive_loop(
    gamepad: Gamepad,
    motors: CarMotors,
    sound: CarSound,
    voice: VoiceLines,
    colorsensor: CarColorSensor,
    settings: Settings,
    audio_player: AudioPlayer,
) -> None:
    """Reads the gamepad and drives the motors until interrupted with Ctrl+C.

    The red boundary line is guarded against in both modes, as an extra safety net: the
    line-follower is expected to stay within its own track, but if it ever does reach the boundary
    line it blocks exactly like free-drive does, rather than assuming that can never happen. A live
    dashboard (laps, speed, mode, ...) updates in place below any one-off messages (errors, mode
    switches, etc.), which keep printing normally.
    """
    line_follow_active = False
    track_tracker = TrackSegmentTracker(settings.line_follow_segment_confirm_ticks)
    line_follower = LineFollower(
        settings.line_follow_small_scan_degrees,
        settings.line_follow_scan_degrees,
        settings.line_follow_look_straight_ticks,
    )
    active_command: TurnCommand | None = None  # last dispatched, still in-flight command -- display only
    boost_sound_delay_remaining = 0
    drive_toggle = DriveToggle()
    goal_count = 0
    boundary_guard = BoundaryGuard()
    was_bumped = False
    was_boosting = False
    was_line_boosting = False
    was_searching = False
    track_acquired = False
    lap_baseline_set = False  # the very first confirmed segment never counts as a lap, even if it's white
    try:
        with Dashboard() as dashboard:
            _set_light(motors, colorsensor, le.LEGO_COLOR_GREEN)  # starts in free-drive mode
            while True:
                gamepad.poll()
                audio_player.update()
                color = colorsensor.detected_color()
                reflection = colorsensor.reflection()

                bumped = motors.is_bumped()
                if bumped and not was_bumped:
                    sound.play_honk()
                    voice.play_voice("crash", queue=True)
                was_bumped = bumped

                on_boundary = color == settings.boundary_color
                is_lifted = colorsensor.is_lifted(reflection, settings.lift_reflection_threshold)
                just_blocked, just_released = boundary_guard.update(on_boundary, is_lifted)
                if just_blocked:
                    sound.play_honk()
                    voice.play_voice("boundaryline", queue=True)
                    _set_light(motors, colorsensor, le.LEGO_COLOR_RED, le.LIGHT_PATTERN_SHORT_BLINK)
                if just_released:
                    motors.release()
                    _set_light(motors, colorsensor, le.LEGO_COLOR_BLUE if line_follow_active else le.LEGO_COLOR_GREEN)
                if boundary_guard.is_blocked:
                    motors.block()
                    # keep edge-detection state current so a held X/Y doesn't fire the instant the block clears
                    gamepad.button_just_pressed(settings.gamepad.button_x)
                    gamepad.button_just_pressed(settings.gamepad.button_y)
                    dashboard.update(
                        mode="LINE-FOLLOWER" if line_follow_active else "FREE-DRIVE",
                        laps=goal_count,
                        speed_left=0,
                        speed_right=0,
                        detail="-",
                        status="BOUNDARY BLOCKED — lift car and place it back inside",
                        controls=_LINE_FOLLOWER_CONTROLS if line_follow_active else _FREE_DRIVE_CONTROLS,
                    )
                    time.sleep(settings.loop_interval_s)
                    continue

                if gamepad.button_just_pressed(settings.gamepad.button_x):
                    line_follow_active = not line_follow_active
                    # start each activation fresh, ignoring prior segment/boost/search history, and
                    # stop driving on the switch so a mode change never carries over a driving intent
                    track_tracker = TrackSegmentTracker(settings.line_follow_segment_confirm_ticks)
                    line_follower.reset()
                    active_command = None
                    boost_sound_delay_remaining = 0
                    drive_toggle.stop()
                    was_boosting = False
                    was_line_boosting = False
                    was_searching = False
                    track_acquired = False
                    lap_baseline_set = False
                    voice.play_instruction("linefollower" if line_follow_active else "freeride")
                    _set_light(motors, colorsensor, le.LEGO_COLOR_BLUE if line_follow_active else le.LEGO_COLOR_GREEN)

                # read every tick (even in free-drive, which ignores it) so A's edge state isn't stale
                # by the time line-follower mode's toggle starts consuming it
                forward_pressed = gamepad.button_just_pressed(settings.gamepad.button_a)

                if line_follow_active:
                    detected_segment = classify_track_segment(
                        color,
                        settings.line_follow_normal_color,
                        settings.line_follow_boost_color,
                        settings.line_follow_goal_color,
                    )
                    on_track = detected_segment is not TrackSegment.NONE

                    if (
                        forward_pressed
                        and drive_toggle.direction is DriveDirection.NONE
                        and detected_segment not in (TrackSegment.NORMAL, TrackSegment.GOAL)
                    ):
                        # can't start driving without a valid blue/white line already under the
                        # sensor -- green, the boundary, or no line at all can't be a starting spot
                        voice.play_voice("losttrack")
                        forward_pressed = False  # swallow the press -- don't let the toggle react to it

                    # backward driving isn't offered by the A-button toggle itself, only the forward press is forwarded
                    forward = direction_to_forward(drive_toggle.update(forward_pressed, False))

                    if forward:
                        # the follower decides each turn as an exact, IMU-verified degree command
                        # -- forward here is just the gate; motor_done reports whether the
                        # previously dispatched command (if any) has finished on the hub yet
                        motor_done = motors.is_done()
                        drive_straight, command, gave_up = line_follower.update(detected_segment, motor_done)
                        if drive_straight:
                            active_command = None
                        elif command is not None:
                            active_command = command
                        elif motor_done:
                            active_command = None
                    else:
                        line_follower.reset()
                        motors.stop()
                        drive_straight, command, gave_up = False, None, False
                        active_command = None

                    if gave_up:
                        sound.play_honk()
                        voice.play_voice("losttrack", queue=True)
                        drive_toggle.stop()
                        motors.stop()
                        track_acquired = False
                        lap_baseline_set = False

                    if on_track and not track_acquired:
                        voice.play_voice("starttrack")
                        track_acquired = True

                    searching = bool(forward) and line_follower.is_searching
                    was_searching = _set_light_on_change(
                        motors,
                        colorsensor,
                        searching,
                        was_searching,
                        le.LEGO_COLOR_RED,
                        le.LEGO_COLOR_BLUE,
                        le.LIGHT_PATTERN_SHORT_BLINK,
                    )

                    entered_new_segment = track_tracker.update(detected_segment)
                    if entered_new_segment:
                        # the very first segment ever confirmed this activation is just "where it
                        # started" -- only a later, genuine transition into white counts as a lap
                        is_first_segment = not lap_baseline_set
                        lap_baseline_set = True
                        if track_tracker.current is TrackSegment.GOAL and not is_first_segment:
                            goal_count += 1
                            sound.play_honk()
                        # delayed so the sound lands after the motor's own ramp has started speeding up
                        boost_sound_delay_remaining = (
                            settings.line_follow_boost_sound_delay_ticks if track_tracker.current is TrackSegment.BOOST else 0
                        )

                    if boost_sound_delay_remaining > 0:
                        boost_sound_delay_remaining -= 1
                        if boost_sound_delay_remaining == 0:
                            sound.play_boost()

                    # boost is continuous for as long as the (debounced) segment is green, not a
                    # one-time pulse -- it's the same continuous scan-and-drive cycle as blue, faster
                    boosting = track_tracker.current is TrackSegment.BOOST
                    was_line_boosting = _set_light_on_change(
                        motors, colorsensor, boosting, was_line_boosting, le.LEGO_COLOR_ORANGE, le.LEGO_COLOR_BLUE
                    )
                    speed_percent = settings.line_follow_boost_speed_percent if boosting else settings.line_follow_speed_percent

                    # a turn command is only dispatched on the tick it's newly issued -- issuing
                    # another command while one is in flight would cancel it on the hub (the one
                    # exception: drive_straight deliberately cancels an in-flight scan to resume)
                    if drive_straight:
                        motors.drive(speed_percent, speed_percent)
                    elif isinstance(command, TurnCommand):
                        motors.turn_for_degrees(command.degrees, settings.line_follow_turn_speed_percent)

                    # dashboard speed display only -- reflects the currently active maneuver (which
                    # may have been dispatched on an earlier tick and still be in flight)
                    if drive_straight:
                        speed_left = speed_right = speed_percent
                    elif isinstance(active_command, TurnCommand):
                        turn_sign = 1.0 if active_command.degrees >= 0 else -1.0
                        speed_left = turn_sign * settings.line_follow_turn_speed_percent
                        speed_right = -turn_sign * settings.line_follow_turn_speed_percent
                    else:
                        speed_left = speed_right = 0.0

                    dashboard.update(
                        mode="LINE-FOLLOWER",
                        laps=goal_count,
                        speed_left=speed_left,
                        speed_right=speed_right,
                        detail=track_tracker.current.name,
                        status="SEARCHING FOR LINE" if searching else ("OK" if forward else "STOPPED"),
                        controls=_LINE_FOLLOWER_CONTROLS,
                    )
                else:
                    forward_held = gamepad.button_held(settings.gamepad.button_a)
                    backward_held = gamepad.button_held(settings.gamepad.button_b)
                    forward = held_to_forward(forward_held, backward_held)
                    turn = gamepad.turn(settings.turn_deadzone)
                    boost_amount = gamepad.boost_amount()
                    throttle = throttle_for_boost(boost_amount, settings.base_speed_percent, settings.max_speed_percent)
                    boosting = boost_amount > 0
                    was_boosting = _set_light_on_change(
                        motors, colorsensor, boosting, was_boosting, le.LEGO_COLOR_ORANGE, le.LEGO_COLOR_GREEN
                    )
                    speed_left, speed_right = arcade_drive(forward, turn, throttle, settings.turn_scale)
                    dashboard.update(
                        mode="FREE-DRIVE",
                        laps=goal_count,
                        speed_left=speed_left,
                        speed_right=speed_right,
                        detail="BOOST" if boost_amount > 0 else "-",
                        status="OK" if forward else "STOPPED",
                        controls=_FREE_DRIVE_CONTROLS,
                    )
                    motors.drive(speed_left, speed_right)

                if gamepad.button_just_pressed(settings.gamepad.button_y):
                    voice.play_voice("comments")

                time.sleep(settings.loop_interval_s)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping...[/yellow]")


def main() -> int:
    banner("Lego Education Car")
    settings = load_settings()

    try:
        motor_card = get_connection_card("Double Motor", settings.motor_card)
        colorsensor_card = get_connection_card("Color Sensor", settings.colorsensor_card)
        gamepad = _connect_gamepad(settings)
    except RuntimeError as exc:
        error(str(exc))
        return 1
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Cancelled.[/yellow]")
        return 1

    if settings.motor_card is None or settings.colorsensor_card is None:
        settings.motor_card = motor_card
        settings.colorsensor_card = colorsensor_card
        save_settings(settings)
        success("Connection Cards saved to settings.json.")

    motors = _connect_motors(CARD_COLORS[motor_card.color_name], motor_card.serial, settings)
    if motors is None:
        gamepad.close()
        return 1

    colorsensor = _connect_colorsensor(CARD_COLORS[colorsensor_card.color_name], colorsensor_card.serial)
    if colorsensor is None:
        motors.disconnect()
        gamepad.close()
        return 1

    audio_player = AudioPlayer()
    sound = CarSound(settings.honk_sound_file, settings.boost_sound_file, audio_player)
    try:
        voice = VoiceLines(settings.language, audio_player)
    except RuntimeError as exc:
        error(str(exc))
        motors.disconnect()
        colorsensor.disconnect()
        gamepad.close()
        return 1

    console.print()
    try:
        _run_drive_loop(gamepad, motors, sound, voice, colorsensor, settings, audio_player)
    finally:
        motors.stop()
        motors.disconnect()
        colorsensor.disconnect()
        gamepad.close()

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception:  # last-resort safety net: a readable traceback beats a raw crash
        console.print_exception()
        exit_code = 1
    raise SystemExit(exit_code)
