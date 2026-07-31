"""Wraps the LEGO Education Double Motor that drives the car's wheels."""

import legoeducation as le


class CarMotors:
    def __init__(self) -> None:
        self._motor = le.DoubleMotor()

    def connect(self, card_color: int, card_serial: str, drive_acceleration: int, drive_deceleration: int) -> bool:
        self._motor.connect(card_color=card_color, card_serial=card_serial)
        if self._motor.connected:
            self._motor.movement_set_end_state(le.MOTOR_END_STATE_COAST)  # no holding torque when idle
            self._motor.movement_set_acceleration(drive_acceleration, drive_deceleration)
        return self._motor.connected

    def drive(self, speed_left: float, speed_right: float) -> None:
        """Drives both tracks continuously, or releases them (coast) if both speeds are 0. Speeds are in percent (-100..100).

        The motor's own acceleration/deceleration ramp (set once in connect()) smooths every speed
        and direction change made this way — forward/backward reversals, boost/non-boost changes,
        and plain speed changes all ride the same ramp, rather than needing separate smoothing code.
        """
        if speed_left == 0 and speed_right == 0:
            self._motor.movement_stop()
            return
        self._motor.movement_move_tank(speed_left=speed_left, speed_right=speed_right)

    def turn_for_degrees(self, degrees: float, speed_percent: float) -> None:
        """Pivots in place by exactly degrees (positive = right, negative = left), non-blocking —
        poll is_done() each tick to know when it's finished. The IMU (gyroscope), not timing,
        confirms when the turn is actually complete, so this is accurate regardless of speed,
        surface friction, or how small degrees is.
        """
        direction = le.MOVEMENT_TURN_DIRECTION_RIGHT if degrees >= 0 else le.MOVEMENT_TURN_DIRECTION_LEFT
        self._motor.movement_turn_for_degrees(abs(degrees), direction=direction, speed=speed_percent, blocking=False)

    def move_for_degrees(self, degrees: float, speed_percent: float) -> None:
        """Drives straight for exactly degrees of wheel rotation (positive = forward, negative =
        backward), non-blocking — poll is_done() each tick to know when it's finished.
        """
        direction = le.MOVEMENT_MOVE_DIRECTION_FORWARD if degrees >= 0 else le.MOVEMENT_MOVE_DIRECTION_BACKWARD
        self._motor.movement_move_for_degrees(abs(degrees), direction=direction, speed=speed_percent, blocking=False)

    def is_done(self) -> bool:
        """Whether the last turn_for_degrees()/move_for_degrees() command has finished."""
        return self._motor.done()

    def is_bumped(self) -> bool:
        """Whether the IMU's last reported gesture is at least a tap — a light, easy-to-trigger bump."""
        return self._motor.imu_gesture.gesture == le.MOTION_GESTURE_TAPPED

    def light(self, color: int, pattern: int = le.LIGHT_PATTERN_SOLID) -> None:
        """Sets the hub's built-in status light — a glance-able mode/state indicator that doesn't
        need the terminal to be visible (see car/main.py for what each color/pattern means). Sent
        non-blocking since it's cosmetic and must never add latency to the drive loop.
        """
        self._motor.light_color(color, pattern=pattern, blocking=False)

    def block(self) -> None:
        """Hard stop: actively holds both wheels in place so they resist being pushed (e.g. red boundary-line safety stop)."""
        self._motor.movement_set_end_state(le.MOTOR_END_STATE_HOLD)
        self._motor.movement_stop()

    def release(self) -> None:
        """Restores normal coast behavior for idle stops — call once it is safe to drive again after block()."""
        self._motor.movement_set_end_state(le.MOTOR_END_STATE_COAST)

    def stop(self) -> None:
        self._motor.movement_stop()

    def disconnect(self) -> None:
        self._motor.disconnect()
