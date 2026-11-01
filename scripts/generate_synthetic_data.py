"""Export labelled deterministic synthetic fixtures; never connects to a database."""

import argparse
import json
from pathlib import Path

from t1d_api.data.synthetic import generate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite an existing fixture")
    data = generate(args.seed, args.count)
    with args.output.open("x") as stream:
        json.dump(data, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print("Synthetic engineering fixture exported; no database writes")


if __name__ == "__main__":
    main()
