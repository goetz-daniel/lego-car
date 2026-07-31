from car.robot.boundary import BoundaryGuard


def test_boundary_guard_starts_free():
    guard = BoundaryGuard()
    assert not guard.is_blocked


def test_boundary_guard_blocks_on_first_boundary_sighting():
    guard = BoundaryGuard()
    just_blocked, just_released = guard.update(on_boundary=True, is_lifted=False)
    assert just_blocked
    assert not just_released
    assert guard.is_blocked


def test_boundary_guard_does_not_release_just_because_the_line_is_gone():
    guard = BoundaryGuard()
    guard.update(on_boundary=True, is_lifted=False)
    just_blocked, just_released = guard.update(on_boundary=False, is_lifted=False)
    assert not just_blocked
    assert not just_released
    assert guard.is_blocked  # must be lifted first, not just driven/pushed off the line


def test_boundary_guard_releases_after_being_lifted_and_placed_back_down_clear():
    guard = BoundaryGuard()
    guard.update(on_boundary=True, is_lifted=False)
    guard.update(on_boundary=True, is_lifted=True)
    just_blocked, just_released = guard.update(on_boundary=False, is_lifted=False)
    assert not just_blocked
    assert just_released
    assert not guard.is_blocked
