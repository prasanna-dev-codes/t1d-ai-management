"""One killable inference process per request, with deadline/RSS admission budgets."""

import json
import multiprocessing as mp
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import numpy as np
import psutil

from t1d_vision.artifacts import load_artifact
from t1d_vision.contracts import (
    Candidate,
    Reason,
    Task,
    VisionAvailability,
    VisionFault,
    VisionResult,
)
from t1d_vision.images import MAX_BYTES, decode, tensor
from t1d_vision.metrics import probabilities

Processor = Callable[[bytes, str, str, str], dict[str, Any]]


def process_image(data: bytes, mime: str, root: str, operation: str) -> dict[str, Any]:
    manifest, graph = load_artifact(Path(root))
    if operation == "status":
        return VisionAvailability(
            available=True,
            supported_tasks=["single_label_classification"],
            model=manifest.info(),
            reason_code="MODEL_READY",
        ).model_dump(mode="json")
    started = time.monotonic()
    decoded = decode(data, mime)
    if operation != "single_label_classification":
        return VisionResult(
            prediction_id=uuid4(),
            status="abstained",
            task=cast(Task, operation),
            model=manifest.info(),
            image_quality=decoded.quality,
            candidates=[],
            reason_codes=["UNSUPPORTED_CAPABILITY"],
            processing_ms=(time.monotonic() - started) * 1000,
            completed_at=datetime.now(UTC),
        ).model_dump(mode="json")
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.log_severity_level = 4
    session = ort.InferenceSession(
        str(graph), sess_options=options, providers=["CPUExecutionProvider"]
    )
    output = session.run(None, {session.get_inputs()[0].name: tensor(decoded.rgb)})[0]
    values = np.asarray(output, dtype=np.float64)
    if values.shape != (1, len(manifest.classes)) or not np.isfinite(values).all():
        raise VisionFault(503, "MODEL_OUTPUT_INVALID")
    scores = probabilities(values, manifest.temperature)[0]
    order = np.argsort(-scores, kind="stable")
    reasons: list[Reason] = []
    if float(scores[order[0]]) < float(manifest.minimum_score or 0):
        reasons.append("LOW_CONFIDENCE")
    if float(scores[order[0]] - scores[order[1]]) < float(manifest.minimum_margin or 0):
        reasons.append("AMBIGUOUS_CLASS")
    candidates = [
        Candidate(
            canonical_id=manifest.classes[int(i)].canonical_id,
            label=manifest.classes[int(i)].label,
            score=float(scores[i]),
        )
        for i in order[:5]
    ]
    result = VisionResult(
        prediction_id=uuid4(),
        status="abstained" if reasons else "review_required",
        task="single_label_classification",
        model=manifest.info(),
        image_quality=decoded.quality,
        candidates=candidates,
        reason_codes=reasons or ["HUMAN_REVIEW_REQUIRED"],
        processing_ms=(time.monotonic() - started) * 1000,
        completed_at=datetime.now(UTC),
    )
    return result.model_dump(mode="json")


def _child(
    connection: Any, incoming: Any, mime: str, root: str, operation: str, processor: Processor
) -> None:
    # Native decoder/runtime diagnostics must not leak paths or media into server logs.
    fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    try:
        data = incoming.recv_bytes(maxlength=MAX_BYTES)
        incoming.close()
        message = {"ok": processor(data, mime, root, operation)}
    except VisionFault as exc:
        message = {"error": {"status": exc.status, "code": exc.code}}
    except BaseException:
        message = {"error": {"status": 503, "code": "VISION_PROCESS_FAILED"}}
    try:
        connection.send_bytes(json.dumps(message, allow_nan=False).encode())
    except (OSError, ValueError, TypeError):
        pass
    finally:
        connection.close()
        incoming.close()


def _feed(connection: Any, data: bytes) -> None:
    try:
        connection.send_bytes(data)
    except OSError:
        pass
    finally:
        connection.close()


class ProcessBudget:
    def __init__(
        self,
        deadline_seconds: float = 5,
        memory_bytes: int = 1024**3,
        processor: Processor = process_image,
    ) -> None:
        if not 0.05 <= deadline_seconds <= 30 or not 32 * 1024**2 <= memory_bytes <= 2 * 1024**3:
            raise ValueError("Invalid process budget")
        self.deadline_seconds = deadline_seconds
        self.memory_bytes = memory_bytes
        self.processor = processor
        self._active = threading.BoundedSemaphore(1)
        self._failed_cleanup = False

    def run(
        self,
        data: bytes,
        mime: str,
        root: str,
        operation: str,
        cancel: threading.Event | None = None,
    ) -> dict[str, Any]:
        if self._failed_cleanup:
            raise VisionFault(503, "VISION_PROCESS_FAILED")
        if len(data) > MAX_BYTES:
            raise VisionFault(413, "PAYLOAD_TOO_LARGE")
        if not self._active.acquire(blocking=False):
            raise VisionFault(503, "VISION_BUSY")
        context = mp.get_context("spawn")
        reader, writer = context.Pipe(duplex=False)
        incoming, outgoing = context.Pipe(duplex=False)
        process = context.Process(
            target=_child,
            args=(writer, incoming, mime, root, operation, self.processor),
            daemon=True,
        )
        feeder = threading.Thread(target=_feed, args=(outgoing, data), daemon=True)
        started_feeder = False
        try:
            before = time.monotonic()
            process.start()
            writer.close()
            incoming.close()
            feeder.start()
            started_feeder = True
            monitor = psutil.Process(process.pid)
            while True:
                if cancel is not None and cancel.is_set():
                    raise VisionFault(408, "VISION_CANCELLED")
                if time.monotonic() - before > self.deadline_seconds:
                    raise VisionFault(504, "VISION_TIMEOUT")
                try:
                    if monitor.memory_info().rss > self.memory_bytes:
                        raise VisionFault(503, "VISION_MEMORY_LIMIT")
                except psutil.NoSuchProcess:
                    pass
                if reader.poll(0.02):
                    try:
                        message = json.loads(reader.recv_bytes(maxlength=128 * 1024))
                    except (EOFError, OSError, ValueError, RecursionError):
                        raise VisionFault(503, "VISION_PROCESS_FAILED") from None
                    if not isinstance(message, dict):
                        raise VisionFault(503, "MODEL_OUTPUT_INVALID")
                    if "error" in message:
                        error = message["error"]
                        allowed = {
                            "INVALID_IMAGE": 422,
                            "PAYLOAD_TOO_LARGE": 413,
                            "UNSUPPORTED_IMAGE_FORMAT": 415,
                            "IMAGE_FORMAT_MISMATCH": 415,
                            "IMAGE_DIMENSIONS": 422,
                            "ANIMATED_IMAGE_UNSUPPORTED": 415,
                            "IMAGE_MODE_UNSUPPORTED": 415,
                            "MODEL_UNAVAILABLE": 503,
                            "MODEL_OUTPUT_INVALID": 503,
                            "VISION_PROCESS_FAILED": 503,
                        }
                        code = error.get("code") if isinstance(error, dict) else None
                        if not isinstance(code, str) or code not in allowed:
                            raise VisionFault(503, "VISION_PROCESS_FAILED")
                        raise VisionFault(allowed[code], code)
                    result = message.get("ok")
                    if not isinstance(result, dict):
                        raise VisionFault(503, "MODEL_OUTPUT_INVALID")
                    return result
                if not process.is_alive():
                    raise VisionFault(503, "VISION_PROCESS_FAILED")
        except (OSError, RuntimeError, psutil.Error):
            raise VisionFault(503, "VISION_PROCESS_FAILED") from None
        finally:
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=0.5)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=0.5)
                if process.is_alive():
                    self._failed_cleanup = True
                else:
                    process.close()
            if started_feeder:
                feeder.join(timeout=0.5)
            incoming.close()
            outgoing.close()
            reader.close()
            writer.close()
            self._active.release()


class VisionRuntime:
    def __init__(self, root: Path | None = None, budget: ProcessBudget | None = None) -> None:
        self.root = root
        self.budget = budget or ProcessBudget()

    def status(self) -> VisionAvailability:
        if self.root is None:
            return VisionAvailability(
                available=False, supported_tasks=[], model=None, reason_code="MODEL_UNAVAILABLE"
            )
        try:
            return VisionAvailability.model_validate(
                self.budget.run(b"", "", str(self.root), "status")
            )
        except (VisionFault, ValueError):
            return VisionAvailability(
                available=False, supported_tasks=[], model=None, reason_code="MODEL_UNAVAILABLE"
            )

    def analyze(
        self, data: bytes, mime: str, task: Task, cancel: threading.Event | None = None
    ) -> VisionResult:
        if self.root is None:
            raise VisionFault(503, "MODEL_UNAVAILABLE")
        try:
            return VisionResult.model_validate(
                self.budget.run(data, mime, str(self.root), task, cancel)
            )
        except ValueError:
            raise VisionFault(503, "MODEL_OUTPUT_INVALID") from None
