"""Run real memory services in disposable containers, without persistent volumes."""

import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from neo4j import GraphDatabase

NEO4J_IMAGE = "neo4j:5.26.0-community"


def main() -> int:
    name = "t1d-memory-tests-" + uuid4().hex[:12]
    password = secrets.token_hex(24)
    started = False
    with tempfile.TemporaryDirectory(prefix="t1d-memory-tests-") as folder:
        envfile = Path(folder) / "neo4j.env"
        envfile.write_text(
            f"NEO4J_AUTH=neo4j/{password}\nNEO4J_server_memory_heap_initial__size=256m\n"
            "NEO4J_server_memory_heap_max__size=512m\nNEO4J_server_memory_pagecache_size=256m\n"
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
                    "t1d.purpose=disposable-memory-tests",
                    "--tmpfs",
                    "/data",
                    "--env-file",
                    str(envfile),
                    "-p",
                    "127.0.0.1::7687",
                    NEO4J_IMAGE,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            started = True
            port = json.loads(
                subprocess.check_output(
                    ["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", name],
                    text=True,
                )
            )["7687/tcp"][0]["HostPort"]
            uri = f"bolt://127.0.0.1:{port}"
            driver = GraphDatabase.driver(
                uri,
                auth=("neo4j", password),
                connection_timeout=2,
                connection_acquisition_timeout=2,
                max_transaction_retry_time=0,
            )
            deadline = time.monotonic() + 180
            while True:
                try:
                    driver.verify_connectivity()
                    break
                except Exception:
                    if time.monotonic() > deadline:
                        raise RuntimeError("Disposable graph startup timeout") from None
                    time.sleep(1)
            driver.close()
            environment = os.environ.copy()
            environment["T1D_TEST_NEO4J_URI"] = uri
            environment["T1D_TEST_NEO4J_PASSWORD"] = password
            print(
                "Running real TimescaleDB/pgvector/Neo4j integration with synthetic records",
                flush=True,
            )
            process = subprocess.Popen(
                [sys.executable, "scripts/run_database_tests.py", *sys.argv[1:]],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            assert process.stdout is not None
            for line in process.stdout:
                print(line.replace(password, "[REDACTED]"), end="", flush=True)
            return process.wait()
        except Exception as exc:
            print(
                f"Disposable memory runner failed: {type(exc).__name__}; diagnostics redacted",
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
