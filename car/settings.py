"""Loads and saves settings.json, the application's actual configuration store (not this module).

Edit settings.json directly, or allow the application to detect values (gamepad calibration,
Connection Cards) and persist them automatically.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parent / "settings.json"


@dataclass
class ConnectionCard:
    """A device's Connection Card: color_name is a key into car.cli.CARD_COLORS."""

    color_name: str
    serial: str


@dataclass
class GamepadCalibration:
    """One controller's detected mapping, produced by car.controller.calibrate.run_calibration().

    Turn and boost are each auto-detected during calibration, so exactly one alternative in each group
    below is set (the rest are None):
    - turn: turn_axis (+turn_axis_invert), or turn_hat, or turn_left_button/turn_right_button
    - boost: boost_axis (+boost_axis_rest/boost_axis_peak), or boost_button
    """

    name: str
    turn_axis: int | None
    turn_axis_invert: bool
    turn_hat: int | None
    turn_left_button: int | None
    turn_right_button: int | None
    button_a: int
    button_b: int
    button_x: int
    button_y: int
    boost_button: int | None
    boost_axis: int | None
    boost_axis_rest: float | None
    boost_axis_peak: float | None


@dataclass
class Settings:
    # Drive loop
    loop_interval_s: float

    # Sound effects (file names, resolved relative to car/assets/effects/)
    honk_sound_file: str
    boost_sound_file: str

    # Spoken comments/instructions: selects the car/assets/<language>/ folder — see car/robot/voice.py
    language: str

    # Free-drive mode
    turn_deadzone: float
    drive_acceleration: int
    drive_deceleration: int
    base_speed_percent: float
    max_speed_percent: float
    turn_scale: float

    # Red boundary-line safety stop (free-drive mode only)
    lift_reflection_threshold: int
    boundary_color: int

    # Line-follower mode
    line_follow_normal_color: int
    line_follow_boost_color: int
    line_follow_goal_color: int
    line_follow_speed_percent: float
    line_follow_boost_speed_percent: float
    line_follow_boost_pulse_ticks: int
    line_follow_boost_sound_delay_ticks: int
    line_follow_segment_confirm_ticks: int

    # Line-follower mode: halt-scan-align-step cycle + retrace-and-broaden recovery, driven by
    # the Double Motor's IMU-verified movement_turn_for_degrees()/movement_move_for_degrees()
    line_follow_look_degrees: float
    line_follow_look_straight_ticks: int
    line_follow_recovery_look_degrees: float
    line_follow_turn_speed_percent: float
    line_follow_scan_turn_speed_percent: float
    line_follow_step_degrees: float
    line_follow_search_speed_percent: float

    # Gamepad calibration wizard
    calibration_axis_hold_s: float
    calibration_axis_noise_threshold: float
    calibration_poll_interval_s: float

    # Detected once, then persisted here
    motor_card: ConnectionCard | None
    colorsensor_card: ConnectionCard | None
    gamepad: GamepadCalibration | None


_STARTING_SETTINGS = Settings(
    loop_interval_s=0.05,
    honk_sound_file="honk.mp3",
    boost_sound_file="boost.mp3",
    language="de",
    turn_deadzone=0.1,
    drive_acceleration=60,
    drive_deceleration=60,
    base_speed_percent=50,
    max_speed_percent=100,
    turn_scale=0.5,
    lift_reflection_threshold=3,
    boundary_color=1,  # le.LEGO_COLOR_RED
    line_follow_normal_color=3,  # le.LEGO_COLOR_BLUE
    line_follow_boost_color=5,  # le.LEGO_COLOR_GREEN
    line_follow_goal_color=7,  # le.LEGO_COLOR_WHITE
    line_follow_speed_percent=12,
    line_follow_boost_speed_percent=100,
    line_follow_boost_pulse_ticks=4,
    line_follow_boost_sound_delay_ticks=2,
    line_follow_segment_confirm_ticks=2,
    line_follow_look_degrees=18.0,  # 5% of a full 360-degree turn
    line_follow_look_straight_ticks=2,
    line_follow_recovery_look_degrees=36.0,  # 10% of a full 360-degree turn
    line_follow_turn_speed_percent=30,
    line_follow_scan_turn_speed_percent=10,  # much slower -- the sensor must catch the line mid-turn
    line_follow_step_degrees=90.0,  # a quarter wheel rotation -- small enough for a curve or a straight alike
    line_follow_search_speed_percent=8,
    calibration_axis_hold_s=5.0,
    calibration_axis_noise_threshold=0.3,
    calibration_poll_interval_s=0.02,
    motor_card=None,
    colorsensor_card=None,
    gamepad=None,
)


def save(settings: Settings) -> None:
    SETTINGS_PATH.write_text(json.dumps(asdict(settings), indent=2) + "\n")


def _load_optional[T](data: dict, key: str, cls: type[T]) -> T | None:
    """Pops key from data and constructs cls(**value), or returns None if it was JSON null."""
    value = data.pop(key)
    return cls(**value) if value is not None else None


def load() -> Settings:
    """Reads settings.json, creating it with starting values on first run."""
    if not SETTINGS_PATH.exists():
        save(_STARTING_SETTINGS)

    data = json.loads(SETTINGS_PATH.read_text())
    motor_card = _load_optional(data, "motor_card", ConnectionCard)
    colorsensor_card = _load_optional(data, "colorsensor_card", ConnectionCard)
    gamepad = _load_optional(data, "gamepad", GamepadCalibration)

    return Settings(gamepad=gamepad, motor_card=motor_card, colorsensor_card=colorsensor_card, **data)
