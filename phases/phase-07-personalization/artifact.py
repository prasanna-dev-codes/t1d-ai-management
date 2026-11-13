"""Versioned offline personalization profile and its calibration parameters."""

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from adaptation import METHODS
from personal_intervals import PersonalIntervals
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

_Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_Radius = Annotated[float, Field(ge=0, allow_inf_nan=False)]
_Four = tuple[_Radius, _Radius, _Radius, _Radius]
_Profile = Literal["frozen-v5", "initial-offset", "rolling-offset", "context-offset"]


class InferenceArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["phase07-chronological-v1"] = "phase07-chronological-v1"
    context_policy: Literal["event-time-replay"] = "event-time-replay"
    point_profiles: tuple[_Profile, _Profile, _Profile, _Profile]
    frozen_profiles: tuple[str, str, str, str]
    model_sha256: dict[str, _Digest] = Field(min_length=1)
    constant_radii: _Four
    normalized_quantile: _Four | None
    calibration_participants: int = Field(ge=0)

    @classmethod
    def read(cls, path: Path) -> tuple["InferenceArtifact", str]:
        payload = path.read_bytes()
        return cls.model_validate_json(payload), hashlib.sha256(payload).hexdigest()

    def verify_models(self, hashes: dict[str, str], profiles: list[str]) -> None:
        if (
            self.model_sha256 != hashes
            or self.frozen_profiles != tuple(profiles)
            or not set(self.point_profiles) <= set(METHODS)
        ):
            raise ValueError("Personalization artifact does not match the frozen point models")

    def intervals(self) -> PersonalIntervals:
        return PersonalIntervals(
            np.asarray(self.constant_radii),
            np.asarray(self.normalized_quantile) if self.normalized_quantile is not None else None,
            self.calibration_participants,
        )


def write_artifact(
    path: Path,
    profiles: list[str],
    frozen_profiles: list[str],
    hashes: dict[str, str],
    local: PersonalIntervals,
) -> None:
    artifact = InferenceArtifact.model_validate(
        {
            "point_profiles": profiles,
            "frozen_profiles": frozen_profiles,
            "model_sha256": hashes,
            "constant_radii": local.constant.tolist(),
            "normalized_quantile": local.normalized_quantile.tolist()
            if local.normalized_quantile is not None
            else None,
            "calibration_participants": local.calibration_participants,
        }
    )
    path.write_text(json.dumps(artifact.model_dump(), indent=2) + "\n", encoding="utf-8")
