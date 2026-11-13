"""Feature projections and artifact composition for the offline history models."""

from typing import Any

import numpy as np

from t1d_forecasting.history_features import HISTORY_CGM_FEATURES
from t1d_forecasting.windows import CGM_FEATURES, FEATURE_NAMES, HISTORY_FEATURE_NAMES

TARGET_SCALE = 20.0
MODEL_COLUMNS = {
    "frozen-v1": tuple(range(len(FEATURE_NAMES))),
    "long-cgm": tuple(range(len(CGM_FEATURES)))
    + tuple(range(len(FEATURE_NAMES), len(FEATURE_NAMES) + len(HISTORY_CGM_FEATURES))),
    "long-context": tuple(range(len(HISTORY_FEATURE_NAMES))),
    "long-context-huber": tuple(range(len(HISTORY_FEATURE_NAMES))),
}
MODEL_WEIGHTS = {name: {name: 1.0} for name in MODEL_COLUMNS}
MODEL_WEIGHTS.update(
    {
        "history-ensemble": {"long-context": 0.5, "long-context-huber": 0.5},
        "baseline-history-ensemble": {
            "frozen-v1": 0.5,
            "long-context": 0.25,
            "long-context-huber": 0.25,
        },
    }
)


def factor_masks(matrix: Any) -> dict[str, Any]:
    column = {name: matrix[:, i] for i, name in enumerate(HISTORY_FEATURE_NAMES)}
    return {
        "cgm": np.ones(len(matrix), dtype=bool),
        "carbs": column["recorded_carbs_240_present"] == 1,
        "insulin_on_board": np.zeros(len(matrix), dtype=bool),
        "insulin_sensitivity_factor": np.zeros(len(matrix), dtype=bool),
        "physical_activity": (column["recorded_exercise_120_present"] == 1)
        | (column["reported_exercise_intensity_240_present"] == 1),
        "sleep_hours": (column["reported_sleep_hours_24_present"] == 1)
        | (column["sensor_sleep_hours_24_present"] == 1),
        "daily_routine": (column["cgm_clock_day_1_present"] == 1)
        | (column["cgm_clock_day_2_present"] == 1)
        | (column["reported_work_hours_24_present"] == 1),
        "early_morning_pattern_proxy": column["prior_morning_pair_present"] == 1,
        "activity_after_insulin": column["reported_exercise_after_bolus_present"] == 1,
        "body_weight_bmi": np.zeros(len(matrix), dtype=bool),
        "insulin_type": column["recorded_insulin_type_present"] == 1,
    }
