from collections import deque

import pytest

from services.batch_evaluation import _format_duration, _timing_text


@pytest.mark.parametrize("seconds, expected", [
    (0, "00:00:00"), (59.9, "00:00:59"), (60, "00:01:00"),
    (3661, "01:01:01"), (90061, "25:01:01"), (-5, "00:00:00"),
])
def test_duration_format(seconds, expected):
    assert _format_duration(seconds) == expected


def test_eta_waits_for_a_new_session_sample():
    assert _timing_text(100, [], 80, now=110) == "Elapsed: 00:00:10 | Remaining: calculating"


def test_eta_uses_remaining_groups_and_recent_average():
    assert _timing_text(100, [10, 20], 4, now=130) == "Elapsed: 00:00:30 | Remaining: ~00:01:00"


def test_eta_rolls_over_old_samples_in_constant_memory():
    durations = deque([1000] * 10, maxlen=10)
    durations.extend([10] * 10)
    assert len(durations) == 10
    assert _timing_text(100, durations, 2, now=140) == "Elapsed: 00:00:40 | Remaining: ~00:00:20"


def test_eta_rounds_up_subsecond_remaining_time():
    assert _timing_text(100, [0.1], 1, now=100.1).endswith("Remaining: ~00:00:01")


def test_completed_resume_needs_no_samples_and_shows_zero_remaining():
    assert _timing_text(100, [], 0, now=100) == "Elapsed: 00:00:00 | Remaining: 00:00:00"
