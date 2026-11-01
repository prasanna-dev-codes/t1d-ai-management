"""Bounded deterministic preprocessing; original bytes are never modified or stored."""

import hashlib
import io
import warnings
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError

from t1d_vision.contracts import ImageQuality, VisionFault

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 16_000_000
PREPROCESSING_VERSION = "rgb-letterbox224-v1"
MEAN = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
STD = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]


@dataclass(frozen=True)
class Decoded:
    rgb: Image.Image
    quality: ImageQuality
    pixel_digest: str
    perceptual_hash: str


def decode(data: bytes, mime: str) -> Decoded:
    if not data or len(data) > MAX_BYTES:
        raise VisionFault(413 if data else 422, "PAYLOAD_TOO_LARGE" if data else "INVALID_IMAGE")
    expected = {"image/jpeg": "JPEG", "image/png": "PNG"}.get(mime)
    if expected is None:
        raise VisionFault(415, "UNSUPPORTED_IMAGE_FORMAT")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format != expected:
                    raise VisionFault(415, "IMAGE_FORMAT_MISMATCH")
                w, h = source.size
                if min(w, h) < 32 or max(w, h) > 8192 or w * h > MAX_PIXELS:
                    raise VisionFault(422, "IMAGE_DIMENSIONS")
                if getattr(source, "n_frames", 1) != 1:
                    raise VisionFault(415, "ANIMATED_IMAGE_UNSUPPORTED")
                if source.mode not in {"RGB", "RGBA", "L", "LA", "P", "CMYK"}:
                    raise VisionFault(415, "IMAGE_MODE_UNSUPPORTED")
                source.verify()
            with Image.open(io.BytesIO(data)) as source:
                source.load()
                flags: list[
                    Literal["COLOR_PROFILE_NOT_APPLIED", "RGB_CONVERTED", "ALPHA_COMPOSITED_WHITE"]
                ] = []
                if source.info.get("icc_profile"):
                    flags.append("COLOR_PROFILE_NOT_APPLIED")
                image = ImageOps.exif_transpose(source)
                if image.mode in {"RGBA", "LA", "P"}:
                    rgba = image.convert("RGBA")
                    background = Image.new("RGBA", rgba.size, "white")
                    image = Image.alpha_composite(background, rgba).convert("RGB")
                    flags.append("ALPHA_COMPOSITED_WHITE")
                else:
                    if image.mode != "RGB":
                        flags.append("RGB_CONVERTED")
                    image = image.convert("RGB")
                # Fresh pixel-only image drops EXIF/ICC and other original metadata.
                rgb = Image.frombytes("RGB", image.size, image.tobytes())
                width, height = rgb.size
                digest = hashlib.sha256(str(rgb.size).encode() + rgb.tobytes()).hexdigest()
                small = np.asarray(rgb.resize((9, 8), Image.Resampling.BILINEAR).convert("L"))
                bits = small[:, 1:] > small[:, :-1]
                value = 0
                for bit in bits.flat:
                    value = (value << 1) | int(bit)
                return Decoded(
                    rgb,
                    ImageQuality(
                        status="warning" if flags else "accepted",
                        width=width,
                        height=height,
                        warnings=flags,
                    ),
                    digest,
                    f"{value:016x}",
                )
    except VisionFault:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise VisionFault(422, "INVALID_IMAGE") from None


def tensor(image: Image.Image) -> NDArray[np.float32]:
    scale = min(224 / image.width, 224 / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    resized = image.resize(size, Image.Resampling.BILINEAR)
    padded = Image.new("RGB", (224, 224), (124, 116, 104))
    padded.paste(resized, ((224 - size[0]) // 2, (224 - size[1]) // 2))
    array = np.asarray(padded, dtype=np.float32).transpose(2, 0, 1) / np.float32(255)
    return np.ascontiguousarray(((array - MEAN) / STD)[None], dtype=np.float32)
