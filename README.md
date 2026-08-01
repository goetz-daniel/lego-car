# LEGO Education Car

A LEGO Education car with manual Bluetooth gamepad control and an autonomous multi-color
line-following mode. Built on the [LEGO Education Python API](https://github.com/LEGO/LEGOEducation).

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)

## Features

- Free-drive: manual gamepad control with proportional turning, reverse, and boost.
- Line-follower: autonomous track driving with a boost segment, a lap-counting finish line, and
  a lost-line search that resumes the instant the line is found again.
- Boundary safety stop: a red tape line blocks the wheels in either mode.
- Sound and voice: honks, boost effects, and spoken driver comments (any language).
- Status light: at-a-glance mode/state indicator on the motor and sensor.
- Auto-calibrating: a one-time wizard detects any gamepad's button/stick layout.
- Live dashboard: mode, lap count, wheel speed, and status in the terminal.

## Hardware

- LEGO Education Double Motor (differential/tank drive)
- LEGO Education Color Sensor (mounted facing down at the front)
- Any Bluetooth gamepad supported by pygame/SDL2
- A Bluetooth speaker, set as the default audio output

## Setup

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m car.main
```

First run prompts for each device's Connection Card and calibrates a new gamepad automatically;
both are saved to `car/settings.json` and never asked again.

## Controls

### Free-Drive

| Input | Action |
| --- | --- |
| A button | Hold to drive forward |
| B button | Hold to drive backward |
| X button | Switch between free-drive and line-follower |
| Y button | Play a random driver comment |
| Stick | Steer left/right |
| Trigger | Boost speed (hold) |
| Ctrl+C | Stop and disconnect |

### Line-Follower

| Input | Action |
| --- | --- |
| A button | Press once to start, again to stop |
| X button | Switch between free-drive and line-follower |
| Y button | Play a random driver comment |
| Ctrl+C | Stop and disconnect |

The terminal shows only the current mode's controls, updating the instant you switch modes.

## Modes

**Free-Drive** — full manual control. Crossing the red boundary line blocks the wheels, honks,
and plays a spoken warning until the car is lifted clear.

**Line-Follower** — toggle with X, start/stop with A. Drives a track built from colored tape:

| Color | Meaning |
| --- | --- |
| Blue | Normal-speed line following |
| Green | Continuous speed boost for as long as it's seen |
| White | Finish line — honks and counts a lap |
| Red | Boundary — blocks the wheels |

The car drives straight ahead as long as it sees blue, green, or white under the sensor. If it
loses the line, it scans for it (widening the search if needed) and resumes automatically; if the
line can't be found at all, it stops, honks, and waits to be repositioned by hand. A press of A
only starts driving if blue or white is already under the sensor. The segment the car starts on
is never counted as a lap — only a later, genuine arrival at white is.

## Status Light

| Color | Meaning |
| --- | --- |
| Green | Free-drive, driving normally |
| Blue | Line-follower, driving normally |
| Orange | Boosting, either mode |
| Red, blinking | Boundary blocked, or line-follower searching |

## Building the Track

- Plain matte electrical tape in distinct colors (blue, green, white, red by default).
- Lay strips seamlessly — no gaps, no overlaps.
- Stretch tape slightly around curves to keep it flat.
- Only one white segment — it's the single finish line.
- Verify detected colors with the sensor and adjust `settings.json` to match your tape.

Surround the track with a red boundary strip a comfortable distance out.

## Configuration

All tunable behavior lives in `car/settings.json`, created with defaults on first run — edit it
directly, or let the app persist detected values (Connection Cards, gamepad mapping) itself.

## Project Layout

| Path | Description |
| --- | --- |
| `car/main.py` | Entry point and drive loop |
| `car/cli.py` | Interactive Connection Card prompt |
| `car/settings.py` | `settings.json` loading and saving |
| `car/ui.py` | Shared console output helpers |
| `car/controller/` | Gamepad input and calibration wizard |
| `car/robot/` | Motor/sensor/sound hardware wrappers and pure drive/track/boundary logic |
| `car/assets/` | Sound effects and spoken comments/instructions |
| `tests/` | pytest suite for the pure-logic modules in `car/robot/` |

## Built With

| Library | Purpose |
| --- | --- |
| [legoeducation](https://github.com/LEGO/LEGOEducation) | LEGO hub/motor/sensor control |
| [pygame-ce](https://pyga.me/) | Gamepad input and audio playback |
| [rich](https://rich.readthedocs.io/) | Terminal UI and live dashboard |

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest                                    # tests
ruff check car/ && ruff format car/                 # lint & format
pymarkdown --config pyproject.toml scan README.md   # markdown lint
```
