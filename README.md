# LEGO Education Car

Control your LEGO Double Motor car with a gamepad, follow a colored-tape track autonomously,
or roam an arena solo. Three drive modes, sounds, voice comments, lap counter, live dashboard.

[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![MIT](https://img.shields.io/badge/license-MIT-22c55e?style=for-the-badge)](LICENSE)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey?style=for-the-badge)

<p align="center">
  <a href="instructions/car-front.jpeg"><img src="instructions/car-front.jpeg" width="45%" alt="Front view of the car on the track"></a>&nbsp;&nbsp;<a href="instructions/car-back.jpeg"><img src="instructions/car-back.jpeg" width="45%" alt="Rear view of the car with minifigures"></a>
</p>

---

## Hardware

The car's physical build is a modified version of lesson B101 *Castle Quest* from the
[LEGO Education Computer Science & AI](https://teach.legoeducation.com/computer-science/lesson/castle-quest/building-instructions) B1 curriculum (8+ kit),
extended with a Bluetooth gamepad, speaker, and custom Python software.

| Part | Role |
| --- | --- |
| LEGO Education Double Motor | Drives the car |
| LEGO Education Color Sensor | Reads the tape (mounted facing down at the front) |
| Computer | Runs Python and connects to the LEGO hardware |
| Bluetooth or USB gamepad | Your controller |
| Speaker | Output for sound effects and voice comments |

> [!IMPORTANT]
> The Color Sensor must be mounted as close to the ground as possible, so it reliably reads the tape colors.

<p align="center">
  <a href="instructions/car-bottom.jpeg"><img src="instructions/car-bottom.jpeg" width="60%" alt="Color sensor mounted facing down at the front of the car"></a>
</p>

---

## Getting Started

### 1. Get the code

Open a terminal in the folder where you want to save the project, then run:

```bash
git clone https://github.com/goetz-daniel/lego-car.git
cd lego-car
```

### 2. Install Python 3.14+

**macOS / Linux with Homebrew:**

```bash
brew install python@3.14
```

**Windows Command Prompt:**

```bat
winget install Python.Python.3.14
```

### 3. Install and run

Make sure your terminal is still in the `lego-car` folder, then run:

**macOS / Linux:**

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m car.main
```

**Windows:**

```bat
py -3.14 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m car.main
```

On first run you'll be asked separately for the **Connection Card** details for the Double Motor
and Color Sensor, followed by a quick gamepad calibration. The results are saved in
`car/settings.json` and reused later. Calibration runs again if you connect a different gamepad.

<p align="center">
  <a href="instructions/car-card.jpeg"><img src="instructions/car-card.jpeg" width="50%" alt="Holding the Connection Card next to the car"></a>
</p>

<p align="center">
  <a href="instructions/setup-terminal.png"><img src="instructions/setup-terminal.png" width="80%" alt="First-run terminal showing Connection Card prompts and gamepad calibration"></a>
</p>

---

## Track Colors

Lay matte electrical tape on the floor in four colors:

| Color | Meaning |
| --- | --- |
| Blue | Normal path |
| Green | Speed boost — faster as long as it's seen |
| White | Finish line — one lap per crossing |
| Red | Boundary — stops/redirects the car |

No gaps or overlaps between strips. Lay red boundary as a double-width strip so it's always detected. If a color isn't recognized, adjust the `*_color` value in `car/settings.json`.

<p align="center">
  <a href="instructions/car-track.jpeg"><img src="instructions/car-track.jpeg" width="70%" alt="Top-down view of the full track with colored tape"></a>
</p>

<p align="center">
  <a href="instructions/car-finish-line.jpeg"><img src="instructions/car-finish-line.jpeg" width="70%" alt="The car at the LEGO finish line gate"></a>
</p>

---

## Controls

### Free-Drive

You steer. Crossing the red boundary locks the wheels until you lift the car clear.

| Input | Action |
| --- | --- |
| A | Hold to drive forward |
| B | Hold to drive backward |
| Configured stick / D-pad / buttons | Steer |
| Configured trigger / shoulder button | Boost |
| X | Next mode |
| Y | Random driver comment |
| Ctrl+C | Quit |

<p align="center">
  <a href="instructions/free-drive-terminal.png"><img src="instructions/free-drive-terminal.png" width="80%" alt="Free-drive terminal dashboard showing mode, speed, and controls"></a>
</p>

### Line-Follower

Use X to select this mode, then press A. The sensor must see blue or white before the car can start.
It drives straight while blue, green, or white is detected. If it loses the line, it stops, waits
briefly, tries a small left/right search, then performs a wider sweep if needed. If the full search
fails, it stops and waits for manual repositioning.

### Adventure

Use X to select this mode, then press A. Place the car inside a red-tape border. It drives by itself,
redirects at the boundary, and chooses new directions randomly.

Both modes share the same controls:

| Input | Action |
| --- | --- |
| A | Press once to start, again to stop |
| X | Next mode |
| Y | Random driver comment |
| Ctrl+C | Quit |

<p align="center">
  <a href="instructions/line-follower-terminal.png"><img src="instructions/line-follower-terminal.png" width="80%" alt="Line-follower terminal dashboard showing lap times and controls"></a>
</p>

---

## Status Light

| Light | Meaning |
| --- | --- |
| Green | Free-Drive mode |
| Blue | Line-Follower mode selected |
| Yellow | Adventure mode selected |
| Orange | Boosting in Free-Drive or Line-Follower |
| Red, blinking | Boundary blocked / line search / Adventure redirect |

---

## Settings & Libraries

All options are stored in `car/settings.json`. If the file is missing, it is created automatically.

| Library | What it does |
| --- | --- |
| [legoeducation](https://github.com/LEGO/LEGOEducation) | Controls the LEGO hubs |
| [pygame-ce](https://github.com/pygame-community/pygame-ce) | Reads the gamepad, plays sounds |
| [rich](https://github.com/Textualize/rich) | Live terminal dashboard |

---

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest
ruff check car/ tests/ && ruff format car/ tests/
pymarkdown --config pyproject.toml scan README.md README_DE.md AGENTS.md
```
