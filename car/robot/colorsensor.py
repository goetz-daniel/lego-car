"""Wraps the LEGO Education Color Sensor, mounted facing down at the front of the car."""

import legoeducation as le


class CarColorSensor:
    def __init__(self) -> None:
        self._sensor = le.ColorSensor()

    def connect(self, card_color: int, card_serial: str) -> bool:
        self._sensor.connect(card_color=card_color, card_serial=card_serial)
        return self._sensor.connected

    def reflection(self) -> int:
        """Raw reflected light intensity (0..100): near 0 means no surface at all (e.g. lifted off the ground)."""
        return self._sensor.sensor.reflection

    def detected_color(self) -> int:
        """The LEGO Color currently seen underneath the sensor (compare to le.LEGO_COLOR_* constants)."""
        return self._sensor.sensor.color

    def is_lifted(self, reflection: int, threshold: int) -> bool:
        """True once reflection drops below threshold: the car has been picked up off the surface."""
        return reflection < threshold

    def light(self, color: int, pattern: int = le.LIGHT_PATTERN_SOLID) -> None:
        """Sets the sensor's own built-in status light — mirrors CarMotors.light() so the same
        state is visible from the front of the car too, not just the Double Motor at the back.
        """
        self._sensor.light_color(color, pattern=pattern, blocking=False)

    def disconnect(self) -> None:
        self._sensor.disconnect()
