"""Reads input from any Bluetooth gamepad supported by pygame/SDL2."""

import os
import time
from collections.abc import Callable

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from car.robot.drive import analog_amount
from car.settings import GamepadCalibration
from car.ui import console, error, success


class Gamepad:
    """Wraps a single pygame joystick and exposes the inputs the Lego Education Car cares about.

    `turn()` needs a calibration (see car.controller.calibrate) applied first via
    `apply_calibration()` — every other method works right after construction.
    """

    def __init__(self) -> None:
        pygame.display.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() == 0:
            raise RuntimeError(
                "No gamepad found. Pair your gamepad via Bluetooth settings first, power it on, then restart this program."
            )

        self._joystick = pygame.joystick.Joystick(0)
        self._joystick.init()
        self._previous_button_state: dict[int, bool] = {}
        self._calibration: GamepadCalibration | None = None

    @property
    def name(self) -> str:
        return self._joystick.get_name()

    def apply_calibration(self, calibration: GamepadCalibration) -> None:
        self._calibration = calibration

    def poll(self) -> None:
        """Pumps the SDL event queue so axis/button state is current. Call once per loop iteration."""
        pygame.event.pump()

    def turn(self, deadzone: float) -> float:
        """Returns -1 (left) .. 1 (right), 0 within deadzone.

        Continuous if the turn control is a stick axis; a plain -1/0/1 from a D-pad hat or two digital
        buttons otherwise.
        """
        calibration = self._calibration
        if calibration.turn_axis is not None:
            raw = self._joystick.get_axis(calibration.turn_axis)
            if calibration.turn_axis_invert:
                raw = -raw
            return raw if abs(raw) >= deadzone else 0.0
        if calibration.turn_hat is not None:
            hat_x, _hat_y = self._joystick.get_hat(calibration.turn_hat)
            return float(hat_x)
        right_held = self.button_held(calibration.turn_right_button)
        left_held = self.button_held(calibration.turn_left_button)
        return float(right_held) - float(left_held)

    def boost_amount(self) -> float:
        """Returns how boosted the control is: 0 (not held) .. 1 (fully pressed).

        Continuous if the boost control is an analog trigger; a plain 0.0/1.0 from a digital button otherwise.
        """
        calibration = self._calibration
        if calibration.boost_button is not None:
            return float(self.button_held(calibration.boost_button))
        raw = self._joystick.get_axis(calibration.boost_axis)
        return analog_amount(raw, calibration.boost_axis_rest, calibration.boost_axis_peak)

    def button_held(self, button_index: int) -> bool:
        """Returns whether the given button is currently held down (level, not edge-triggered)."""
        return bool(self._joystick.get_button(button_index))

    def button_just_pressed(self, button_index: int) -> bool:
        """Returns True only on the frame a button transitions from released to pressed (edge-triggered)."""
        is_pressed = bool(self._joystick.get_button(button_index))
        was_pressed = self._previous_button_state.get(button_index, False)
        self._previous_button_state[button_index] = is_pressed
        return is_pressed and not was_pressed

    def raw_axes(self) -> list[float]:
        return [round(value, 2) for value in self._read_indices(self._joystick.get_numaxes, self._joystick.get_axis)]

    def raw_buttons(self) -> list[bool]:
        return [bool(value) for value in self._read_indices(self._joystick.get_numbuttons, self._joystick.get_button)]

    def raw_hats(self) -> list[tuple[int, int]]:
        return self._read_indices(self._joystick.get_numhats, self._joystick.get_hat)

    @staticmethod
    def _read_indices(count_getter: Callable[[], int], value_getter: Callable[[int], object]) -> list:
        """Reads pygame's per-index values 0..count-1; shared by raw_axes/raw_buttons/raw_hats."""
        return [value_getter(i) for i in range(count_getter())]

    def close(self) -> None:
        pygame.joystick.quit()
        pygame.display.quit()


def _print_live_mapping() -> None:
    """Debug utility: prints live axis/button/hat values, e.g. to diagnose an unsupported controller."""
    try:
        gamepad = Gamepad()
    except RuntimeError as exc:
        error(str(exc))
        return

    success(f"Connected to: {gamepad.name}")
    console.print("Move sticks/triggers/D-pad and press buttons. Press Ctrl+C to stop.")
    try:
        while True:
            gamepad.poll()
            line = f"axes={gamepad.raw_axes()} buttons={gamepad.raw_buttons()} hats={gamepad.raw_hats()}"
            console.print(line + " " * 10, end="\r")
            time.sleep(0.1)
    except KeyboardInterrupt:
        console.print()
    finally:
        gamepad.close()


if __name__ == "__main__":
    _print_live_mapping()
