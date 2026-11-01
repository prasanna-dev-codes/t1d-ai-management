"""Metadata-only cloud/local probe; no download, training, credentials or cloud provisioning."""

import argparse
import json
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any


def report() -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for name in [
        "torch",
        "torchvision",
        "Pillow",
        "numpy",
        "onnx",
        "onnxruntime",
        "onnxscript",
        "psutil",
    ]:
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {
        "schema_version": "1.0",
        "python": platform.python_version(),
        "python_compatible": sys.version_info[:2] == (3, 12),
        "platform": sys.platform,
        "architecture": platform.machine(),
        "packages": packages,
        "gpu_verified": False,
        "rights_verified": False,
        "persistent_storage_verified": False,
        "training_authorized": False,
        "next_step": "Human approval of environment, data rights, persistent "
        "storage and measured GPU pilot required. No credentials or device identifiers inspected.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    content = json.dumps(report(), indent=2) + "\n"
    if args.output:
        # Exclusive creation avoids silently replacing an experiment's environment record.
        with args.output.open("x") as stream:
            stream.write(content)
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
