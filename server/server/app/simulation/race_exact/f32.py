"""Float32 arithmetic helpers; transcendental wrappers remain provisional.

numpy float32 scalars round every operation to float32 (NumPy 2 keeps Python
scalars "weak", so `F(x) * 0.1` stays float32 like C# `x * 0.1f`).
The powf/log10f wrappers below compute in double and round once. This is
provisional: executing the Global client's native kernels established one-bit
differences for ordinary inputs. JP UI double-call wrappers matched the tested
sample, but hidden server call sites remain unknown. See the continued research
section in docs/RACE_EXACT_PORT.md and native_math_audit.json.
"""

from __future__ import annotations

import math

import numpy as np

F = np.float32
ZERO = F(0.0)
ONE = F(1.0)


def powf(x, y) -> np.float32:
    return F(math.pow(float(x), float(y)))


def log10f(x) -> np.float32:
    return F(math.log10(float(x)))


def sqrtf(x) -> np.float32:
    return np.sqrt(F(x))


def clampf(v, lo, hi) -> np.float32:
    """Mathf.Clamp(v, lo, hi)."""
    if v < lo:
        return F(lo)
    if v > hi:
        return F(hi)
    return F(v)


_EPS8 = F(1.401298464324817e-45) * F(8.0)   # Mathf.Epsilon (denormal min) * 8


def approximately(a, b) -> bool:
    """UnityEngine.Mathf.Approximately (float32, as compiled at 0x8283e0)."""
    a = F(a)
    b = F(b)
    return max(F(max(abs(a), abs(b)) * F(1e-06)), _EPS8) > abs(F(b - a))


def floor_to_int(x) -> int:
    return int(math.floor(float(x)))
