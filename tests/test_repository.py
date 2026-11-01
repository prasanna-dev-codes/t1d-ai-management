"""Prevent source/templates disappearing behind broad inherited ignore patterns."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "path",
    [
        "apps/web/src/lib/api.ts",
        "apps/web/src/lib/api.test.ts",
        "apps/api/.env.example",
        "apps/web/.env.example",
        "infrastructure/docker/.env.example",
        "uv.lock",
        "package-lock.json",
    ],
)
def test_required_source_and_templates_are_not_ignored(path: str) -> None:
    assert (ROOT / path).is_file()
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--no-index", path], cwd=ROOT, check=False
    )
    assert result.returncode == 1, f"Required source/configuration ignored: {path}"
