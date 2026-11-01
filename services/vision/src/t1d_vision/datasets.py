"""Offline rights-gated manifests and conservative source/duplicate-group splitting."""

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from t1d_vision.contracts import Contract, VisionFault
from t1d_vision.images import decode

Split = Literal["train", "validation", "calibration", "test"]


class SourceManifest(Contract):
    dataset_id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=128)
    source_url: str = Field(min_length=1, max_length=512)
    rights_reference: str = Field(min_length=1, max_length=512)
    approval_reference: str | None = None
    acquisition_approved: bool = False
    training_approved: bool = False
    engineering_only: bool = False

    def require_access(self, training: bool = False) -> None:
        if self.engineering_only:
            if self.source_url != "authored-synthetic-software-fixture":
                raise ValueError("Engineering fixtures must be explicitly authored")
            return
        if (
            not self.approval_reference
            or not self.acquisition_approved
            or (training and not self.training_approved)
        ):
            raise ValueError("Explicit dataset rights/access approval required")


class ImageRecord(Contract):
    record_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    relative_path: str
    canonical_id: str = Field(pattern=r"^food\.[a-z][a-z0-9_]*$")
    source_group: str | None = Field(default=None, min_length=1, max_length=128)
    file_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pixel_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    perceptual_hash: str = Field(pattern=r"^[a-f0-9]{16}$")
    official_split: Literal["train", "test"] | None = None

    @model_validator(mode="after")
    def local(self) -> "ImageRecord":
        p = Path(self.relative_path)
        if p.is_absolute() or ".." in p.parts or "\\" in self.relative_path:
            raise ValueError("Unsafe manifest path")
        return self


class QualityIssue(Contract):
    record_index: int = Field(ge=0)
    code: Literal["CORRUPT_IMAGE", "UNMAPPED_LABEL", "UNSAFE_PATH", "SOURCE_GROUP_MISSING"]


class DatasetIndex(Contract):
    source: SourceManifest
    taxonomy_version: str
    records: list[ImageRecord]
    issues: list[QualityIssue]


def safe_path(root: Path, relative: str) -> Path:
    base = root.resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError("Unsafe/missing manifest file")
    return path


def index_directory(
    root: Path,
    source: SourceManifest,
    taxonomy_version: str,
    label_map: dict[str, str],
    groups: dict[str, str] | None = None,
) -> DatasetIndex:
    source.require_access()
    records = []
    issues = []
    paths = sorted(p for p in root.rglob("*") if p.is_file())
    for index, path in enumerate(paths):
        relative = path.relative_to(root).as_posix()
        try:
            resolved = safe_path(root, relative)
        except ValueError:
            issues.append(QualityIssue(record_index=index, code="UNSAFE_PATH"))
            continue
        label = label_map.get(path.parent.name)
        if label is None:
            issues.append(QualityIssue(record_index=index, code="UNMAPPED_LABEL"))
            continue
        try:
            if resolved.stat().st_size > 8 * 1024 * 1024:
                raise VisionFault(413, "PAYLOAD_TOO_LARGE")
            data = resolved.read_bytes()
            mime = "image/png" if data.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
            decoded = decode(data, mime)
        except (OSError, VisionFault):
            issues.append(QualityIssue(record_index=index, code="CORRUPT_IMAGE"))
            continue
        file_hash = hashlib.sha256(data).hexdigest()
        identity = hashlib.sha256(
            (
                source.dataset_id + "\0" + source.version + "\0" + relative + "\0" + file_hash
            ).encode()
        ).hexdigest()
        group = (groups or {}).get(relative)
        if group is None:
            issues.append(QualityIssue(record_index=index, code="SOURCE_GROUP_MISSING"))
        records.append(
            ImageRecord(
                record_id=identity,
                relative_path=relative,
                canonical_id=label,
                source_group=group,
                file_sha256=file_hash,
                pixel_sha256=decoded.pixel_digest,
                perceptual_hash=decoded.perceptual_hash,
            )
        )
    return DatasetIndex(
        source=source, taxonomy_version=taxonomy_version, records=records, issues=issues
    )


def duplicate_groups(
    records: list[ImageRecord], threshold: int = 5, max_bucket: int = 256
) -> dict[str, str]:
    if not 0 <= threshold <= 5:
        raise ValueError("Supported perceptual threshold is 0–5")
    if len({r.record_id for r in records}) != len(records):
        raise ValueError("Duplicate manifest identities")
    parents = {r.record_id: r.record_id for r in records}
    labels = {r.record_id: r.canonical_id for r in records}

    def find(key: str) -> str:
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    def union(a: str, b: str) -> None:
        a, b = find(a), find(b)
        if a != b:
            parents[max(a, b)] = min(a, b)

    known: dict[tuple[str, str], str] = {}
    buckets: dict[tuple[int, int], list[ImageRecord]] = defaultdict(list)
    # Six disjoint bands guarantee a candidate for <=5 changed bits; dense buckets fail closed.
    shifts = [(0, 11), (11, 11), (22, 11), (33, 11), (44, 10), (54, 10)]
    for row in sorted(records, key=lambda r: r.record_id):
        for kind, value in [
            ("file", row.file_sha256),
            ("pixels", row.pixel_sha256),
            ("source", row.source_group),
        ]:
            if value is None:
                continue
            key = (kind, value)
            if key in known:
                if kind in {"file", "pixels"} and labels[known[key]] != row.canonical_id:
                    raise ValueError("Exact duplicate label conflict")
                union(row.record_id, known[key])
            else:
                known[key] = row.record_id
        bits = int(row.perceptual_hash, 16)
        candidates: dict[str, ImageRecord] = {}
        keys = []
        for band, (shift, width) in enumerate(shifts):
            band_key = (band, (bits >> shift) & ((1 << width) - 1))
            keys.append(band_key)
            for prior in buckets[band_key]:
                candidates[prior.record_id] = prior
        for prior in candidates.values():
            if (bits ^ int(prior.perceptual_hash, 16)).bit_count() <= threshold:
                union(row.record_id, prior.record_id)
        for band_key in keys:
            if len(buckets[band_key]) >= max_bucket:
                raise ValueError("Perceptual audit bucket limit; review before splitting")
            buckets[band_key].append(row)
    return {row.record_id: find(row.record_id) for row in records}


class SplitPlan(Contract):
    seed: int
    assignments: dict[str, Split]
    groups: dict[str, str]
    excluded_training_ids: list[str]
    limitations: list[str]


def split_records(records: list[ImageRecord], seed: int = 42) -> SplitPlan:
    groups = duplicate_groups(records)
    members: dict[str, list[ImageRecord]] = defaultdict(list)
    for row in records:
        members[groups[row.record_id]].append(row)
    assignments: dict[str, Split] = {}
    excluded = []
    eligible = []
    for identity, rows in members.items():
        if any(r.official_split == "test" for r in rows):
            for row in rows:
                if row.official_split == "test":
                    assignments[row.record_id] = "test"
                else:
                    excluded.append(row.record_id)
        else:
            eligible.append(identity)
    roles: list[Split] = ["train", "validation", "calibration"]
    if len(eligible) < 3:
        raise ValueError("Insufficient independent groups for train/validation/calibration")
    eligible.sort(key=lambda value: hashlib.sha256(f"{seed}:{value}".encode()).hexdigest())
    target = {"train": 0.8, "validation": 0.1, "calibration": 0.1}
    counts = {role: 0 for role in roles}
    for index, identity in enumerate(eligible):
        # Seed all roles, then fill proportional group sizes; never split a group.
        role = roles[index] if index < 3 else min(roles, key=lambda r: counts[r] / target[r])
        for row in members[identity]:
            assignments[row.record_id] = role
        counts[role] += len(members[identity])
    limitations = [
        "Group fractions are approximate; class balance must be audited before training."
    ]
    if any(r.source_group is None for r in records):
        limitations.append("Source session groups missing; no session independence claim.")
    plan = SplitPlan(
        seed=seed,
        assignments=assignments,
        groups=groups,
        excluded_training_ids=sorted(excluded),
        limitations=limitations,
    )
    validate_split(plan)
    return plan


def validate_split(plan: SplitPlan) -> None:
    seen: dict[str, Split] = {}
    for identity, role in plan.assignments.items():
        if identity not in plan.groups:
            raise ValueError("Split identity missing group")
        group = plan.groups[identity]
        if group in seen and seen[group] != role:
            raise ValueError("Cross-split group leakage")
        seen[group] = role
    if set(plan.excluded_training_ids) & set(plan.assignments):
        raise ValueError("Excluded row assigned to split")


def validate_boxes(boxes: list[list[float]], class_count: int) -> None:
    """Rows are [class_id,left,top,width,height], normalized; not YOLO center xywh."""
    import math

    if class_count < 1:
        raise ValueError("Positive class count required")

    for box in boxes:
        if len(box) != 5 or not all(math.isfinite(v) for v in box):
            raise ValueError("Invalid box")
        label, x, y, w, h = box
        if (
            label != int(label)
            or not 0 <= label < class_count
            or min(w, h) <= 0
            or min(x, y) < 0
            or x + w > 1
            or y + h > 1
        ):
            raise ValueError("Invalid normalized box/class")


def validate_mask(mask: object, allowed_ids: set[int], shape_hw: tuple[int, int]) -> None:
    import numpy as np

    if min(shape_hw) < 1 or not allowed_ids or any(identity < 0 for identity in allowed_ids):
        raise ValueError("Invalid mask schema")
    values = np.asarray(mask)
    if (
        values.shape != shape_hw
        or not np.issubdtype(values.dtype, np.integer)
        or not set(np.unique(values).tolist()) <= allowed_ids
    ):
        raise ValueError("Invalid categorical mask/shape")
