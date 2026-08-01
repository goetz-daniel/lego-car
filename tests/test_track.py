from car.robot.track import TrackSegment, TrackSegmentTracker, classify_track_segment

NORMAL, BOOST, GOAL = 3, 5, 7


def test_classify_track_segment_maps_known_colors():
    assert classify_track_segment(NORMAL, NORMAL, BOOST, GOAL) is TrackSegment.NORMAL
    assert classify_track_segment(BOOST, NORMAL, BOOST, GOAL) is TrackSegment.BOOST
    assert classify_track_segment(GOAL, NORMAL, BOOST, GOAL) is TrackSegment.GOAL


def test_classify_track_segment_unknown_color_is_none():
    assert classify_track_segment(99, NORMAL, BOOST, GOAL) is TrackSegment.NONE


def test_tracker_starts_on_none():
    tracker = TrackSegmentTracker(confirm_ticks=2)
    assert tracker.current is TrackSegment.NONE


def test_tracker_requires_confirm_ticks_before_switching():
    tracker = TrackSegmentTracker(confirm_ticks=2)
    assert tracker.update(TrackSegment.NORMAL) is False
    assert tracker.current is TrackSegment.NONE
    assert tracker.update(TrackSegment.NORMAL) is True
    assert tracker.current is TrackSegment.NORMAL


def test_tracker_ignores_a_single_stray_misread():
    tracker = TrackSegmentTracker(confirm_ticks=2)
    tracker.update(TrackSegment.NORMAL)
    tracker.update(TrackSegment.NORMAL)
    assert tracker.current is TrackSegment.NORMAL

    tracker.update(TrackSegment.BOOST)  # one stray tick reading the wrong segment
    assert tracker.current is TrackSegment.NORMAL

    tracker.update(TrackSegment.NORMAL)  # back to normal before the stray reading could be confirmed
    assert tracker.current is TrackSegment.NORMAL
