"""Personal uncertainty must use mature history and fall back when unsupported."""

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest
from adaptation import WARMUP, replay
from personal_intervals import calibrate
from test_adaptation import START, row


def test_personal_scale_ignores_late_and_future_outcomes() -> None:
    observed = [row(hour) for hour in range(24)]
    current = row(168, glucose=900)
    late = replace(row(166, glucose=800), label_available_at=current.cutoff + timedelta(seconds=1))
    combined = observed + [late, current]
    result = replay(
        combined,
        np.full((len(combined), 4), 100.0),
        START + WARMUP,
        [True] * len(combined),
        estimate_recent_error=True,
    )
    assert np.isnan(result.recent_error[:-1]).all()
    assert result.recent_error[-1] == pytest.approx([30] * 4)


def test_calibration_preserves_constant_fallback_and_adapts_supported_width() -> None:
    rows = [replace(row(0), participant=str(index)) for index in range(3)]
    residual = np.asarray([[amount] * 4 for amount in (10, 20, 30)])
    constant = np.full(4, 30)
    output = calibrate(rows, residual, residual, constant)
    assert output.calibration_participants == 3
    radii = output.radii([[np.nan] * 4, [10] * 4, [50] * 4])
    assert radii[0] == pytest.approx(constant)
    assert (radii[1] < radii[2]).all()
    unsupported = calibrate(rows[:2], residual[:2], residual[:2], constant)
    assert unsupported.radii([[60] * 4])[0] == pytest.approx(constant)
