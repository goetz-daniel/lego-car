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

- `LineStepper` is a discrete "halt, scan, decide, align, step forward" cycle — the car
  translates only during a step; it never drives while scanning or aligning. This supersedes an
  earlier "never halt, continuous driving" design (see repo memory for that history) — the car
  now genuinely stops translating for every scan/align, by explicit user request.
- Every turn/step is an exact, IMU-verified command — `LineStepper` never mixes a small turn
  fraction into continuous throttle (`arcade_drive`) the way it originally did. That approach
  could produce a wheel-speed differential too small to overcome the motors' own static friction
  at low speeds/angles, so the car would silently fail to move at all during a scan. Instead,
  `car/robot/motors.py`'s `turn_for_degrees()`/`move_for_degrees()` wrap the Double Motor's own
  `movement_turn_for_degrees()`/`movement_move_for_degrees()`, which use the hub's IMU (gyroscope)
  to confirm the turn/move is actually complete — accurate regardless of speed, surface friction,
  or how small the angle is. These are dispatched non-blocking (`blocking=False`) and polled via
  `CarMotors.is_done()` each tick, so the main loop stays responsive; `LineStepper.update()` takes
  `motor_done` as a parameter and only advances to the next phase once it's `True`. `LineStepper`
  itself stays pure (no hardware I/O, per Architecture above) — it expresses intent by returning a
  `TurnCommand`/`MoveCommand` (see `car/robot/drive.py`), and `car/main.py` is what actually calls
  into `CarMotors`.
- Each cycle: come to a translational halt and pivot through three brief looks — dead ahead, then
  left, then right (`line_follow_look_degrees` off of straight ahead, dead-ahead held for
  `line_follow_look_straight_ticks` ticks since it needs no motor command), reading the sensor
  only during these three looks. Whichever direction (if any) saw the line becomes that cycle's
  found position; the car then pivots back (`ALIGN`) to face exactly that position — skipped
  entirely if it's already facing it (found to the right, since the last look was look-right) —
  before driving straight forward for a step (`STEP`). A step is never second-guessed partway
  through, since the car is already aimed exactly where the line was last confirmed.
- Every step is the same fixed `line_follow_step_degrees`, whether the found position was dead
  ahead or a curve, and regardless of track segment (`NORMAL`/`GOAL` alike) — small enough to
  re-check a sharp curve often, and never so large a straight-looking step can carry the car
  outside the line before the next scan catches a curve starting. Deliberately no adaptive
  min/max "trust" sizing here — the only thing that differs on a curve at all is inherent to
  aligning off-center: the `ALIGN` swing to face a found left/right position is naturally bigger
  than the (zero-length, skipped) swing for a dead-ahead find, so a curve doesn't need any extra
  step-sizing logic to already be handled cautiously. The green `BOOST` segment is guaranteed
  straight for its whole length, so `LineStepper.update()` skips scanning entirely there and
  returns no command at all — `car/main.py` drives straight through continuously via
  `CarMotors.drive()` instead, the one deliberate exception to "always the same step size" (there's
  nothing to scan for on a guaranteed-straight strip, so going faster there is safe).
- If a scan finds the line nowhere, this doesn't panic immediately: it first always straightens
  back to center (undoing whatever this cycle's own look-left/look-right ended up pointed at) —
  this straightening happens even when there's no step history to retrace, so the following
  re-scan is never left centered off by a stale heading offset. Then, if any steps have been taken
  yet, it backs up exactly the distance covered by the last couple of them (retracing the path it
  just drove, since that's the last place the line was confirmed) — skipped only if there's no
  step history yet (e.g. right at startup) — and re-scans with a wider
  `line_follow_recovery_look_degrees`; a tight curve entered too fast is often recoverable this
  way. Only if that broader re-scan also finds nothing does `update()` report `gave_up`, honking,
  playing `"losttrack"`, and stopping — the one safety net kept from every prior design. A
  recovery that does find the line resumes with the same fixed `line_follow_step_degrees` step,
  and the retraced step history is cleared the moment it's consumed — so a later miss retraces
  only the distance actually covered since the last recovery, never a stale mix of pre- and
  post-recovery step lengths. Do not reintroduce a continuous per-tick wiggle or a persisted
  heading-bias "compass" — this design is deliberately discrete halted cycles, not continuous, and
  recovery is deliberately a fixed two-stage retrace-then-broaden, not a cycle-count patience
  threshold.
- `line_follow_turn_speed_percent` is a dedicated, always-adequate speed used for every
  `turn_for_degrees()` call, independent of the move speed (`line_follow_speed_percent`/
  `line_follow_search_speed_percent`/`line_follow_boost_speed_percent`) — turns and moves are
  fundamentally different motions (pivot vs. straight-line), so they don't need to share one
  speed value, and decoupling them is what fixes the old "didn't turn at all" bug.
- The look-left/look-right sweep turns use their own, much slower
  `line_follow_scan_turn_speed_percent` instead of `line_follow_turn_speed_percent` — unlike a
  blind align/recovery-straighten pivot (which already knows where it's going and needs no
  sensor reading mid-turn), a scan sweep must let the sensor actually register the line at the
  correct moment, which a fast turn can blow straight past. `TurnCommand.is_scan` (set only on
  the two look-transition turns in `LineStepper`) is what lets `car/main.py` pick the right speed
  without `drive.py` needing to know about hardware speeds at all.
- Segment detection uses the categorical LEGO Color, not raw RGB/HSV — more lighting-tolerant,
  and a single sensor has no positional offset to steer on anyway.
- `car/main.py`'s `track_acquired` flag plays the `"starttrack"` comment the moment the track
  is (re)found — once on mode activation, and once again each time the car reacquires the track
  after a `gave_up` stop (both reset it to `False`). It is deliberately NOT reset on every brief
  mid-curve loss/reacquisition, so ordinary curve driving never replays it.
- Green only boosts for `line_follow_boost_pulse_ticks` ticks on entry, not the whole segment
  (avoids overshoot on the next curve).
- The red boundary line is guarded against in both modes identically, even though line-follower
  isn't expected to reach it.
- While a `turn_for_degrees()`/`move_for_degrees()` command is in flight (`motor_done` is
  `False`), never call `CarMotors.drive()`/issue another for-degrees command on top of it — that
  would cancel the in-flight command on the hub rather than queuing after it. This is why
  `car/main.py` only dispatches a new command on the tick `LineStepper.update()` actually returns
  one (not on every tick), and why turning the master forward gate off calls `motors.stop()`
  explicitly rather than relying on a `speed=0` `drive()` call to cut an in-flight turn/move.

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
  from `car/main.py`'s `_FREE_DRIVE_CONTROLS`/`_LINE_FOLLOWER_CONTROLS` — pass the matching one at
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
