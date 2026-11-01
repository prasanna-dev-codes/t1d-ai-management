"""Future authorized-dataset boundary. No external connector or download implementation."""

import hashlib
import hmac
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from t1d_api.data.schemas import Input, Kind, Opaque


class ImportManifest(Input):
    dataset_id: Opaque
    version: Opaque
    source_ref: Opaque
    license_reference: Opaque
    access_authorized: bool = False
    license_verified: bool = False
    synthetic: bool = False
    schema_mapping_version: Opaque
    unit_mapping_version: Opaque
    timezone_mapping_version: Opaque
    pseudonymization_namespace: Opaque
    split_strategy: Opaque
    split_manifest_ref: Opaque | None = None
    limitations: list[str] = Field(min_length=1, max_length=20)

    def require_acquisition_authority(self) -> None:
        if not self.access_authorized or not self.license_verified:
            raise ValueError("Access and license verification required before import")


@dataclass(frozen=True)
class CanonicalRecord:
    subject_ref: str
    kind: Kind
    payload: dict[str, Any]


class ValidationIssue(Input):
    record_index: int = Field(ge=0)
    code: Literal[
        "INVALID_FORMAT",
        "INVALID_UNIT",
        "INVALID_TIMESTAMP",
        "MISSING_PROVENANCE",
        "DUPLICATE",
        "QUARANTINED",
    ]


class AdapterValidationReport(Input):
    dataset_id: Opaque
    version: Opaque
    records_seen: int = Field(ge=0)
    accepted: int = Field(ge=0)
    rejected: int = Field(ge=0)
    quarantined: int = Field(ge=0)
    issues: list[ValidationIssue] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def totals(self) -> "AdapterValidationReport":
        if self.records_seen != self.accepted + self.rejected + self.quarantined:
            raise ValueError("Report counts must partition observed records")
        if any(issue.record_index >= self.records_seen for issue in self.issues):
            raise ValueError("Issue index outside observed records")
        return self


class DatasetAdapter(Protocol):
    def validate(self, manifest: ImportManifest) -> AdapterValidationReport: ...

    def records(self, manifest: ImportManifest) -> Iterable[CanonicalRecord]: ...


def pseudonymize(subject: str, namespace: str, key: bytes) -> str:
    if len(key) < 32 or not subject or not namespace:
        raise ValueError("Explicit strong linkage key and namespace required")
    return hmac.new(key, (namespace + "\0" + subject).encode(), hashlib.sha256).hexdigest()
