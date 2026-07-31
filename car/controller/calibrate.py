"""Detects a gamepad's mapping (turn stick/D-pad/buttons, A/B/X/Y buttons, boost trigger/button) by
asking the user to move or press each one in turn.
"""

import time

from car.controller.gamepad import Gamepad
from car.settings import GamepadCalibration, Settings, load as load_settings
from car.ui import console, error


def _wait_for_press(gamepad: Gamepad, poll_interval_s: float) -> int:
    """Polls until any button is pressed, returning its index. Waits indefinitely; only Ctrl+C gives up."""
    while True:
        gamepad.poll()
        for index, pressed in enumerate(gamepad.raw_buttons()):
            if pressed:
                return index
        time.sleep(poll_interval_s)


def _wait_for_release(gamepad: Gamepad, button_index: int, poll_interval_s: float) -> None:
    """Blocks until the given button is released, so the next detection starts from a clean state."""
    while gamepad.raw_buttons()[button_index]:
        gamepad.poll()
        time.sleep(poll_interval_s)


def _detect_control(
    gamepad: Gamepad, hold_seconds: float, noise_threshold: float, poll_interval_s: float, watch_hats: bool = True
) -> tuple[str, int, float, float]:
    """Samples every button, D-pad hat (if watch_hats), and axis in windows of hold_seconds, waiting
    indefinitely for one of them to move or be pressed; only Ctrl+C gives up. A button press wins over
    a D-pad hat, which wins over incidental axis noise.

    Returns (kind, index, rest_value, peak_value): kind is "button", "hat", or "axis". rest_value/
    peak_value are only meaningful when kind is "axis": rest is the axis's resting value, peak is the
    most extreme value observed, used to tell a full-range stick from a trigger and to normalize how
    far the latter is pressed.
    """
    baseline = gamepad.raw_axes()
    while True:
        deadline = time.monotonic() + hold_seconds
        best_axis_index, best_axis_delta, best_axis_value = None, noise_threshold, 0.0
        pressed_button_index = None
        moved_hat_index = None
        while time.monotonic() < deadline:
            gamepad.poll()
            for index, pressed in enumerate(gamepad.raw_buttons()):
                if pressed:
                    pressed_button_index = index
            if watch_hats:
                for index, (hat_x, _hat_y) in enumerate(gamepad.raw_hats()):
                    if hat_x != 0:
                        moved_hat_index = index
            for index, value in enumerate(gamepad.raw_axes()):
                delta = abs(value - baseline[index])
                if delta > best_axis_delta:
                    best_axis_index, best_axis_delta, best_axis_value = index, delta, value
            time.sleep(poll_interval_s)
        if pressed_button_index is not None:
            return "button", pressed_button_index, 0.0, 0.0
        if moved_hat_index is not None:
            return "hat", moved_hat_index, 0.0, 0.0
        if best_axis_index is not None:
            return "axis", best_axis_index, baseline[best_axis_index], best_axis_value


def _detect_button(gamepad: Gamepad, label: str, poll_interval_s: float) -> int:
    """Prompts for a labeled button, waits for its press and release, and returns its index."""
    console.print(f"Press the [bold]{label}[/bold] button...")
    index = _wait_for_press(gamepad, poll_interval_s)
    console.print(f"  -> button {index}\n")
    _wait_for_release(gamepad, index, poll_interval_s)
    return index


def _detect_turn(
    gamepad: Gamepad, hold_seconds: float, noise_threshold: float, poll_interval_s: float
) -> tuple[int | None, bool, int | None, int | None, int | None]:
    """Detects the turn control: a stick axis or D-pad (steers both ways on its own), or two separate
    buttons for left/right if neither moved.

    Returns (turn_axis, turn_axis_invert, turn_hat, turn_left_button, turn_right_button).
    """
    console.print("Push and hold the [bold]turn stick or D-pad[/bold] to the left, or hold a [bold]turn-left[/bold] button...")
    kind, index, rest, peak = _detect_control(gamepad, hold_seconds, noise_threshold, poll_interval_s)
    if kind == "axis":
        console.print(f"  -> axis {index}\n")
        return index, peak > rest, None, None, None
    if kind == "hat":
        console.print(f"  -> D-pad (hat {index})\n")
        return None, False, index, None, None
    console.print(f"  -> button {index}\n")
    _wait_for_release(gamepad, index, poll_interval_s)
    turn_right_button = _detect_button(gamepad, "turn right", poll_interval_s)
    return None, False, None, index, turn_right_button


def _detect_boost(
    gamepad: Gamepad, hold_seconds: float, noise_threshold: float, poll_interval_s: float
) -> tuple[int | None, int | None, float | None, float | None]:
    """Detects the boost control: an analog trigger (proportional depth) or a digital shoulder button.
    Returns (boost_button, boost_axis, boost_axis_rest, boost_axis_peak).
    """
    console.print("Hold the [bold]boost[/bold] trigger or shoulder button (RB/RT) for a few seconds...")
    kind, index, rest, peak = _detect_control(gamepad, hold_seconds, noise_threshold, poll_interval_s, watch_hats=False)
    if kind == "axis":
        console.print(f"  -> axis {index}\n")
        return None, index, rest, peak
    console.print(f"  -> button {index}\n")
    _wait_for_release(gamepad, index, poll_interval_s)
    return index, None, None, None


def run_calibration(gamepad: Gamepad, settings: Settings) -> GamepadCalibration:
    """Interactively detects one controller's mapping. Waits indefinitely for each input; only Ctrl+C gives up."""
    console.print("[bold]Gamepad setup[/bold]: move or press each input when prompted, one at a time.\n")
    poll_interval_s = settings.calibration_poll_interval_s
    hold_seconds = settings.calibration_axis_hold_s
    noise_threshold = settings.calibration_axis_noise_threshold

    turn_axis, turn_axis_invert, turn_hat, turn_left_button, turn_right_button = _detect_turn(
        gamepad, hold_seconds, noise_threshold, poll_interval_s
    )

    button_a = _detect_button(gamepad, "A", poll_interval_s)
    button_b = _detect_button(gamepad, "B", poll_interval_s)
    button_x = _detect_button(gamepad, "X", poll_interval_s)
    button_y = _detect_button(gamepad, "Y", poll_interval_s)

    boost_button, boost_axis, boost_axis_rest, boost_axis_peak = _detect_boost(
        gamepad, hold_seconds, noise_threshold, poll_interval_s
    )

    return GamepadCalibration(
        name=gamepad.name,
        turn_axis=turn_axis,
        turn_axis_invert=turn_axis_invert,
        turn_hat=turn_hat,
        turn_left_button=turn_left_button,
        turn_right_button=turn_right_button,
        button_a=button_a,
        button_b=button_b,
        button_x=button_x,
        button_y=button_y,
        boost_button=boost_button,
        boost_axis=boost_axis,
        boost_axis_rest=boost_axis_rest,
        boost_axis_peak=boost_axis_peak,
    )


if __name__ == "__main__":
    try:
        gamepad = Gamepad()
    except RuntimeError as exc:
        error(str(exc))
    else:
        try:
            calibration = run_calibration(gamepad, load_settings())
            console.print(calibration)
        finally:
            gamepad.close()
