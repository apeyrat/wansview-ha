from __future__ import annotations

import io

import numpy as np
from PIL import Image

BLOCK = 16
DELTA = 25


def _gray(img: Image.Image) -> np.ndarray:
    w, h = img.size
    # The top 10 % holds the burnt-in timestamp, different on every capture.
    return np.asarray(img.convert("L").crop((0, h // 10, w, h)), dtype=np.float64)


def _blocks(a: np.ndarray) -> np.ndarray:
    h, w = (a.shape[0] // BLOCK) * BLOCK, (a.shape[1] // BLOCK) * BLOCK
    return a[:h, :w].reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK).mean((1, 3))


def changed_share(prev: bytes, cur: bytes) -> float:
    """Share (0-1) of blocks whose brightness moved by more than DELTA, exposure shift removed."""
    a = Image.open(io.BytesIO(prev))
    b = Image.open(io.BytesIO(cur))
    if b.size != a.size:
        b = b.resize(a.size)
    x, y = _gray(a), _gray(b)
    y += x.mean() - y.mean()
    return float((np.abs(_blocks(x) - _blocks(y)) > DELTA).mean())
