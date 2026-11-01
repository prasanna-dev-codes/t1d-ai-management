"""Inventory/verify a prepared cloud handoff, never download or execute its contents."""

import argparse
import json
from pathlib import Path

from t1d_vision.handoff import inventory, verify_inventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--write-index", action="store_true")
    args = parser.parse_args()
    if args.write_index:
        result = inventory(args.root)
        with (args.root / "bundle-index.json").open("x") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
    else:
        result = verify_inventory(args.root)
    print(
        f"PASS: {len(result['files'])} allowlisted export files; "
        "{result['total_bytes']} bytes. No checkpoint deserialized."
    )


if __name__ == "__main__":
    main()
