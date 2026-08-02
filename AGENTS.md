# Agent Notes for This Repository

Conventions and known pitfalls for anyone — human or AI agent — working on this codebase.

## Setup

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m car.main
```

- The venv is not portable (absolute path baked into `VIRTUAL_ENV`) — recreate with
  `python3.14 -m venv .venv` if the repo folder moves, rather than moving it.
- Use `pygame-ce`, not `pygame` (no Python 3.14 wheel on macOS) — it's still imported as `pygame`.

## Architecture

- `car/robot/`: pure logic with no hardware I/O (`drive.py`, `track.py`, `boundary.py` — unit
  tested) vs. thin hardware/audio wrappers (`colorsensor.py`, `motors.py`, `sound.py`, `voice.py`,
  `audio.py` — not unit tested). New logic belongs on the pure side.
- `car/main.py` orchestrates everything in `_run_drive_loop()`. Connection helpers all route
  through the shared `_connect_device()` — don't duplicate that logic.
- `Settings` (`car/settings.py`) has no Python default values — every value comes from
  `settings.json`. `_STARTING_SETTINGS` is the bootstrap-only exception.
- Gamepad button/axis indices are never hardcoded; `car/controller/calibrate.py` detects and
  saves a mapping per `gamepad.name`.
- `CarMotors.is_bumped()` checks `MOTION_GESTURE_TAPPED` — a light, easy-to-trigger bump, by
  design (not the much harsher `MOTION_GESTURE_COLLISION`).
- Free-drive (A/B hold-to-drive) and line-follower (A press-once-to-toggle via `DriveToggle`) are
  intentionally different interaction models for manual vs. autonomous — don't unify them.
- The Double Motor has no steering axle — turning is purely differential (`arcade_drive()`'s
  `turn_scale`), not Ackermann/axle-based.

## Line Following

- `LineFollower` (`car/robot/drive.py`) is pure logic: `update(segment, motor_done)` returns
  `(drive_straight, command, gave_up)`. `car/main.py` dispatches any returned `TurnCommand` to
  `CarMotors.turn_for_degrees()` — only issue a new command on the tick one is returned, never on
  a `None` tick, or it cancels one still in flight on the hub.
- Drives straight while blue/green/white is seen — no per-tick steering, since the track is built
  only from straight tape strips joined at angles, never curves. Green is a continuous speed
  boost for as long as it's seen.
- On loss: halts, dwells dead ahead, then a small left/right nudge (catches most losses, which are
  just a bit off-center), then a much wider sweep if that finds nothing — stopping and resuming
  straight the instant any look, even mid-sweep, sees the line again. If the wide sweep also finds
  nothing, `gave_up=True` and the car stops for manual repositioning — deliberately no backing up
  or retrying (see `/memories/repo/` for why prior, more elaborate designs were dropped).
- `line_follow_turn_speed_percent` is used for every scan turn — deliberately slow so the sensor
  can actually catch the line mid-turn.
- A only starts driving if blue or white is already under the sensor; other colors reject the
  press with the `"losttrack"` voice line.
- The first segment confirmed after (re)activating never counts as a lap, even if white
  (`lap_baseline_set` in `car/main.py`) — a later genuine arrival at white always does.
- Segment detection uses the categorical LEGO Color, not raw RGB/HSV — lighting-tolerant, and a
  single fixed sensor has no positional offset to steer on anyway.
- `"starttrack"` plays once per track (re)acquisition, not on every brief mid-drive rescan.
- The red boundary stop applies in FREE and LINE modes; adventure mode handles red autonomously
  via `AdventureDriver`'s redirect turn — the `BoundaryGuard` is bypassed entirely in adventure.

## Audio

- `car/robot/audio.py`'s `AudioPlayer` is the single shared `pygame.mixer.Channel` every sound
  (effects + voice) plays through, so sounds never overlap. `play_now()` interrupts immediately
  (standalone events); `play_next()` waits for the current sound to finish first (paired sounds,
  e.g. a honk followed by a comment). Call `update()` once per tick to start a pending
  `play_next()` sound once the channel goes idle.
- `VoiceLines` picks a random clip per category, never repeating the last one played. Adding a
  language or comment is a filesystem-only change (`car/assets/<language>/...`) — never hardcode
  a language name or clip count in code.

## Status Light

- Mirrored on both hubs via `_set_light()` in `car/main.py` — always call that, never
  `motors.light()`/`colorsensor.light()` directly.
- Edge-triggered toggles (searching, boosting) go through `_set_light_on_change()` instead of
  hand-rolling `if changed: set light; store state`.
- See README's Status Light table for current color/pattern meanings — keep it in sync.

## Conventions

- Reuse existing DRY helpers rather than re-duplicating their pattern: `_connect_device()`,
  `Gamepad._read_indices()`, `_load_optional[T]()` in `car/settings.py`, `DriveToggle`/
  `direction_to_forward()`, and `ui.Dashboard` (in-place live stats — never plain `console.print()`
  for per-tick telemetry). `Dashboard.update()`'s `controls` argument is the current mode's rows
  from `car/main.py`'s `_FREE_DRIVE_CONTROLS`/`_TOGGLE_CONTROLS` — pass the matching one at
  every call site so the live display always reflects the active mode, never a stale one.
- Prefer a built-in LEGO Education library function over hand-rolled logic — e.g. the Double
  Motor's own acceleration ramp already smooths every speed change; don't add a second,
  software-side ramp on top of it.
- Error handling: catch expected/recoverable failures locally with `try`/`except` + `ui.error()`;
  let everything else propagate to the single top-level `except Exception` in `car/main.py`.

## Changing the `Settings` Schema

1. Add the new field to `_STARTING_SETTINGS` too.
2. Regenerate `car/settings.json` via a terminal command, not an editor tool (see Known Pitfalls).

Never write migration/fallback code for an outdated `settings.json` — remove old fields outright
from `Settings`/`_STARTING_SETTINGS` and regenerate the file instead.

## Known Pitfalls

- **Editor buffer vs. disk desync**: edit tools can report success, and `read_file` can reflect a
  change, while the bytes on disk haven't caught up yet. Verify with a terminal `cat` before
  running anything that depends on the file.
- `Gamepad.close()` must call only `pygame.joystick.quit()`/`pygame.display.quit()`, never the
  global `pygame.quit()` (would also tear down `CarSound`'s mixer).
- `python -m car.controller.gamepad > file.log 2>&1` buffers stdout fully without a TTY — use
  `python3 -u` for live output when redirecting.
- Bluetooth gamepads can go idle and still show "Connected" while SDL no longer detects them —
  power-cycle the controller, or press a button, to wake it.

## Verification Workflow

```bash
python3 -m py_compile car/*.py car/controller/*.py car/robot/*.py tests/*.py
ruff check car/ tests/
ruff format --check car/ tests/
python -m pytest
```

Follow with a smoke test: import `car.main` and round-trip `car.settings.load()`.

## Tooling

- **pytest** — covers pure-logic modules only (`car/robot/drive.py`, `track.py`, `boundary.py`).
  `python -m pytest`.
- **ruff** — lint and format, line length 130. `ruff check car/` / `ruff format car/`.
- **pymarkdownlnt** — `pymarkdown --config pyproject.toml scan README.md AGENTS.md`.
- All three are dev-only, installed via `pip install -r requirements-dev.txt`.

## Git

The user handles all commits. Do not run `git add`, `git commit`, `git push`, or any other git
write operation. Read-only commands (`status`, `diff`, `log`, `check-ignore`) are fine.
