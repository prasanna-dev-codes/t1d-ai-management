"""Create new ignored local Phase 02 credentials; never overwrite or display them."""

import os
import secrets
import subprocess
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "infrastructure/docker/.env.phase02"
    result = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=root, check=False)
    if result.returncode != 0:
        raise SystemExit("Refusing to create credentials outside ignored configuration")
    if path.exists():
        raise SystemExit("Existing local credentials preserved; no changes made")
    admin, runtime = secrets.token_hex(32), secrets.token_hex(32)
    content = (
        f"PHASE02_ADMIN_PASSWORD={admin}\nPHASE02_RUNTIME_PASSWORD={runtime}\n"
        f"T1D_MIGRATION_DATABASE_URL=postgresql+psycopg://t1d_migrator:{admin}"
        "@127.0.0.1:5434/t1d_phase02\n"
        f"T1D_DATABASE_URL=postgresql+psycopg://t1d_runtime:{runtime}"
        "@127.0.0.1:5434/t1d_phase02\n"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(content)
    print("Ignored mode-0600 local configuration created; credentials not displayed")


if __name__ == "__main__":
    main()
