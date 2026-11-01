"""Run isolated synthetic integration tests; never use persistent Compose volumes."""

import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

IMAGE = (
    "timescale/timescaledb:2.29.0-pg17-oss@sha256:"
    "1a34ea7d1472a57a8d6384a492ffece6d20e4079e81b765833675077cf98b207"
)


def main() -> int:
    name = "t1d-p2-tests-" + uuid4().hex[:12]
    admin = secrets.token_hex(32)
    runtime = secrets.token_hex(32)
    started = False
    stage = "container startup"
    with tempfile.TemporaryDirectory(prefix="t1d-p2-") as directory:
        envfile = Path(directory) / ".env"
        envfile.write_text(
            "POSTGRES_PASSWORD=" + admin + "\nPOSTGRES_DB=t1d_tests\nTIMESCALEDB_TELEMETRY=off\n"
        )
        envfile.chmod(0o600)
        try:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--detach",
                    "--rm",
                    "--name",
                    name,
                    "--label",
                    "t1d.purpose=disposable-tests",
                    "--tmpfs",
                    "/var/lib/postgresql/data",
                    "--env-file",
                    str(envfile),
                    "-p",
                    "127.0.0.1::5432",
                    IMAGE,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            started = True
            deadline = time.monotonic() + 120
            while True:
                probe = subprocess.run(
                    [
                        "docker",
                        "exec",
                        name,
                        "pg_isready",
                        "-h",
                        "127.0.0.1",
                        "-U",
                        "postgres",
                        "-d",
                        "t1d_tests",
                    ],
                    capture_output=True,
                )
                if probe.returncode == 0:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("Disposable database startup timed out")
                time.sleep(0.3)
            stage = "host connection and role provisioning"
            port = json.loads(
                subprocess.check_output(
                    ["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", name],
                    text=True,
                )
            )["5432/tcp"][0]["HostPort"]
            admin_url = f"postgresql://postgres:{admin}@127.0.0.1:{port}/t1d_tests"
            with psycopg.connect(admin_url, autocommit=True) as connection:
                connection.execute(
                    sql.SQL(
                        "CREATE ROLE t1d_runtime LOGIN NOSUPERUSER NOCREATEDB "
                        "NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}"
                    ).format(sql.Literal(runtime))
                )
            stage = "pytest execution"
            environment = os.environ.copy()
            environment["T1D_TEST_ADMIN_URL"] = admin_url
            environment["T1D_TEST_RUNTIME_PASSWORD"] = runtime
            environment.pop("T1D_DATABASE_URL", None)
            print(
                "Running integration tests on a new RAM-backed database; no persistent "
                "volumes attached",
                flush=True,
            )
            process = subprocess.Popen(
                [sys.executable, "-m", "pytest", "tests/integration", "-q", *sys.argv[1:]],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            assert process.stdout is not None
            for line in process.stdout:
                print(
                    line.replace(admin, "[REDACTED]").replace(runtime, "[REDACTED]"),
                    end="",
                    flush=True,
                )
            return process.wait()
        except Exception as exc:
            print(
                f"Database test runner failed at {stage}: {type(exc).__name__}; "
                "sensitive diagnostics suppressed",
                file=sys.stderr,
            )
            return 1
        finally:
            if started:
                subprocess.run(
                    ["docker", "stop", "--time", "15", name], capture_output=True, check=False
                )


if __name__ == "__main__":
    raise SystemExit(main())
