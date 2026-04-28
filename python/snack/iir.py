"""
snack.iir — IIR filter for the Snack DSP core.

Provides a NumPy-first IIR filter that:
* Accepts and returns NumPy float32 arrays.
* Is deterministic by default (noise=0, dither=0).
* Delegates to the compiled C binding (_snack.iir_filter) when available.
* Falls back to a pure Python/NumPy reference implementation otherwise.

Public API
----------
iir_filter(x, b, a=None, channels=1, noise=0.0, dither=0.0, seed=1,
           deterministic=True, return_metadata=False)
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional, Sequence, Union

__all__ = ["iir_filter"]

# Version of the snack_core IIR kernel exposed through this module.
_CORE_VERSION = "0.1.0"


def iir_filter(
    x,
    b: Sequence[float],
    a: Optional[Sequence[float]] = None,
    channels: int = 1,
    noise: float = 0.0,
    dither: float = 0.0,
    seed: int = 1,
    deterministic: bool = True,
    return_metadata: bool = False,
):
    """Apply an IIR filter to *x* and return the filtered output.

    Parameters
    ----------
    x : array-like, shape ``(n_frames * channels,)``, dtype float32
        Input samples, interleaved across channels.
        For mono audio ``channels=1`` this is just a 1-D array of samples.
    b : sequence of float
        Numerator (feedforward) coefficients.
    a : sequence of float, optional
        Denominator (feedback) coefficients.  Defaults to ``[1.0]``
        (pure FIR / no feedback).  ``a[0]`` must be non-zero.
    channels : int
        Number of interleaved audio channels.  Default ``1``.
    noise : float
        Amplitude of additive Gaussian noise.  Ignored when
        ``deterministic=True`` (the default).
    dither : float
        Amplitude of triangular dither.  Ignored when
        ``deterministic=True`` (the default).
    seed : int
        RNG seed used when ``noise`` or ``dither`` are non-zero.
        Providing the same seed guarantees identical output.  Default ``1``.
    deterministic : bool
        When ``True`` (the default), force ``noise=0`` and ``dither=0``
        regardless of the values passed for those parameters.
    return_metadata : bool
        When ``True``, return a ``(y, metadata)`` tuple where *metadata*
        is a dict with algorithm, parameters, version, and input hash.

    Returns
    -------
    y : numpy.ndarray, dtype float32
        Filtered output, same shape as *x*.
    metadata : dict
        Only present when ``return_metadata=True``.

    Notes
    -----
    * Uses the compiled C binding (``_snack.iir_filter``) when available.
    * Falls back to a pure NumPy reference implementation otherwise.
    * The pure NumPy fallback uses Python loops and is not optimised for
      large arrays; it is intended as a reference / test vehicle.
    """
    import numpy as np

    if a is None:
        a = [1.0]

    x = np.asarray(x, dtype=np.float32)
    b_arr = list(b)
    a_arr = list(a)

    if deterministic:
        noise = 0.0
        dither = 0.0

    try:
        from . import _snack as _c

        if not hasattr(_c, "iir_filter"):
            raise AttributeError("C extension does not export iir_filter")

        raw = _c.iir_filter(
            x,
            b_arr,
            a_arr,
            channels,
            noise,
            dither,
            seed,
        )
        y = np.frombuffer(bytes(raw), dtype=np.float32).copy()

    except (ImportError, AttributeError):
        y = _iir_filter_numpy(x, b_arr, a_arr, channels, noise, dither, seed)

    if not return_metadata:
        return y

    params = {
        "b": b_arr,
        "a": a_arr,
        "channels": channels,
        "noise": noise,
        "dither": dither,
        "seed": seed,
        "deterministic": deterministic,
    }
    input_hash = "sha256:" + hashlib.sha256(x.tobytes()).hexdigest()
    metadata = {
        "algorithm": "iir",
        "parameters": params,
        "version": _CORE_VERSION,
        "hash": input_hash,
    }
    return y, metadata


def _iir_filter_numpy(x, b, a, channels: int = 1,
                      noise: float = 0.0, dither: float = 0.0, seed: int = 1):
    """Pure NumPy reference IIR filter (Direct Form I).

    This is a Python-loop implementation intended for correctness testing
    and use when the C extension is not available.  It is not optimised
    for large arrays.

    Implements:
        a[0]*y[n] = sum_j b[j]*x[n-j] - sum_j a[j]*y[n-j]  (j >= 1 for a)

    Stochastic additions (noise, dither) use Python's random.Random seeded
    with *seed*, so results are reproducible for the same seed.
    """
    import numpy as np
    import random

    x = np.asarray(x, dtype=np.float64)
    b = [float(v) for v in b]
    a = [float(v) for v in a]
    n_b = len(b)
    n_a = len(a)
    a0 = a[0]

    n_total = len(x)
    n_frames = n_total // channels
    y = np.zeros(n_total, dtype=np.float64)

    rng = random.Random(seed)

    for i in range(n_frames):
        for ch in range(channels):
            idx = i * channels + ch

            # Feedforward sum
            out = 0.0
            for j in range(n_b):
                fi = i - j
                if fi >= 0:
                    out += b[j] * float(x[fi * channels + ch])

            # Feedback sum
            for j in range(1, n_a):
                fi = i - j
                if fi >= 0:
                    out -= a[j] * y[fi * channels + ch]

            out /= a0

            if noise != 0.0:
                # Approximate Gaussian via 12-uniform-sum (mean 0, var 1)
                g = sum(rng.random() - rng.random() for _ in range(6))
                out += noise * g
            if dither != 0.0:
                out += dither * (rng.random() - rng.random())

            y[idx] = out

    return y.astype(np.float32)
