"""snack.interop — Bridges between snack Sound objects and the scientific
Python audio ecosystem (NumPy, librosa, torchaudio/PyTorch).

All ecosystem imports are deferred so that numpy, torch, and librosa
remain *optional* runtime dependencies.  If an integration function is
called without the required package installed, an ImportError is raised
with a helpful install hint.

Canonical audio data contract
------------------------------
* **Shape**  : ``(channels, frames)`` for multi-channel;
               ``(frames,)`` for mono  (matching librosa convention).
* **Dtype**  : ``numpy.float32``
* **Range**  : ``[-1.0, 1.0]``
* **Channel order**: left channel first (matches librosa and torchaudio; for
  stereo this is ``[left, right]``).

Encoding → numpy dtype mapping
---------------------------------

==============  ============  ===================================
Snack encoding  numpy dtype   divisor to reach ±1.0
==============  ============  ===================================
LIN16           int16         32768.0
LIN32           int32         2147483648.0
SNACK_FLOAT     float32       1.0  (already in [-1, 1])
SNACK_DOUBLE    float64       1.0  (already in [-1, 1])
LIN8            int8          128.0
LIN8OFFSET      uint8         128.0  (subtract 128 first to centre)
LIN24           int32*        8388608.0  (*promoted via Snack)
ALAW / MULAW    —             (decoded to LIN16 first via Snack)
==============  ============  ===================================
"""

import warnings

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_numpy():
    try:
        import numpy as np
        return np
    except ImportError:
        raise ImportError(
            "NumPy is required for this function.\n"
            "Install it with:  pip install numpy"
        ) from None


def _require_torch():
    try:
        import torch
        return torch
    except ImportError:
        raise ImportError(
            "PyTorch is required for this function.\n"
            "Install it with:  pip install torch"
        ) from None


# Encoding integer IDs — kept in sync with generic/jkAudIO.h and the
# constants exported by _snack.
_LIN16 = 1
_ALAW = 2
_MULAW = 3
_LIN8OFFSET = 4
_LIN8 = 5
_LIN24 = 6
_LIN32 = 7
_SNACK_FLOAT = 8
_SNACK_DOUBLE = 9

# Map encoding id → (numpy dtype, divisor to reach [-1.0, 1.0]).
# Divisor is only applied when normalize=True.
_ENCODING_INFO = {
    _LIN16:        ("int16",   32768.0),
    _LIN8:         ("int8",    128.0),
    _LIN8OFFSET:   ("uint8",   128.0),   # needs centring too; see to_numpy()
    _LIN32:        ("int32",   2147483648.0),
    _SNACK_FLOAT:  ("float32", 1.0),
    _SNACK_DOUBLE: ("float64", 1.0),
}

# Human-readable names used to (re-)construct a Sound with a given encoding.
_ENCODING_TO_NAME = {
    _LIN16:       "Lin16",
    _ALAW:        "Alaw",
    _MULAW:       "Mulaw",
    _LIN8OFFSET:  "Lin8offset",
    _LIN8:        "Lin8",
    _LIN24:       "Lin24",
    _LIN32:       "Lin32",
    _SNACK_FLOAT: "Float",
    _SNACK_DOUBLE: "Double",
}

# ---------------------------------------------------------------------------
# NumPy interoperability
# ---------------------------------------------------------------------------


def to_numpy(sound, normalize=True, dtype=None):
    """Convert a :class:`snack.Sound` to a NumPy array.

    Parameters
    ----------
    sound : snack.Sound
        The sound object to convert.
    normalize : bool, default True
        When *True* the sample values are scaled to the ``[-1.0, 1.0]``
        floating-point range regardless of the original encoding.
        When *False* the raw integer or float values are returned using the
        native dtype for the encoding.
    dtype : numpy dtype or None
        Output dtype.  When *None* and *normalize* is ``True``, the output
        dtype is ``float32``; when *normalize* is ``False`` the native dtype
        for the encoding is used.

    Returns
    -------
    numpy.ndarray
        Shape ``(frames,)`` for mono, ``(channels, frames)`` for
        multi-channel audio.

    Raises
    ------
    ImportError
        If NumPy is not installed.
    ValueError
        If the sound encoding is not supported.
    """
    np = _require_numpy()

    encoding = sound.encoding
    nchans = sound.channels
    nframes = sound.length

    if nframes == 0:
        shape = (nchans, 0) if nchans > 1 else (0,)
        out_dtype = np.float32 if (normalize or dtype is None) else np.int16
        arr = np.empty(shape, dtype=dtype if dtype is not None else out_dtype)
        return arr

    # ALAW, MULAW, and LIN24 are first decoded within Snack to a supported
    # integer format so the conversion logic stays simple.
    if encoding in (_ALAW, _MULAW, _LIN24):
        from . import Sound
        if encoding in (_ALAW, _MULAW):
            target_enc = "Lin16"
        else:  # LIN24 → LIN32 (promotes to int32 inside Snack)
            target_enc = "Lin32"
        enc_name = _ENCODING_TO_NAME.get(encoding, "Lin16")
        tmp = Sound(
            sample_rate=sound.sample_rate,
            channels=nchans,
            encoding=enc_name,
        )
        tmp.data(sound.data())      # copy raw bytes into tmp
        tmp.convert(encoding=target_enc)  # decode in-place
        try:
            return to_numpy(tmp, normalize=normalize, dtype=dtype)
        finally:
            tmp.destroy()

    if encoding not in _ENCODING_INFO:
        raise ValueError(
            f"Unsupported Snack encoding id {encoding}. "
            "Supported: LIN16, LIN8, LIN8OFFSET, LIN32, SNACK_FLOAT, "
            "SNACK_DOUBLE, LIN24, ALAW, MULAW."
        )

    raw_bytes = sound.data()
    np_dtype_name, divisor = _ENCODING_INFO[encoding]
    # Use native byte order (Snack stores samples in the platform's native order
    # after reading from any file format).
    arr = np.frombuffer(raw_bytes, dtype=np.dtype(np_dtype_name))

    total_samples = nframes * nchans
    arr = arr[:total_samples]  # guard against any trailing padding in raw bytes

    if encoding == _LIN8OFFSET:
        # uint8 is centred at 128; shift to signed range before dividing.
        arr = arr.astype(np.float32) - np.float32(128.0)
        if normalize:
            arr /= np.float32(divisor)
    elif normalize:
        if encoding in (_SNACK_FLOAT, _SNACK_DOUBLE):
            arr = arr.astype(np.float32)
        else:
            arr = arr.astype(np.float32) / np.float32(divisor)

    # Reshape interleaved samples to (channels, frames).
    # Snack interleaves: [ch0s0, ch1s0, ch0s1, ch1s1, …]
    if nchans > 1:
        arr = arr.reshape(nframes, nchans)
        arr = np.ascontiguousarray(arr.T)  # (channels, frames), C-contiguous
    # else arr is already (frames,)

    if dtype is not None:
        arr = arr.astype(dtype)

    return arr


def from_numpy(arr, sample_rate=16000):
    """Create a :class:`snack.Sound` from a NumPy array.

    The input array should follow the **canonical contract**:

    * **Shape** ``(frames,)`` for mono or ``(channels, frames)`` for
      multi-channel audio.
    * **Dtype** any numeric type.  Floating-point arrays must be in the
      ``[-1.0, 1.0]`` range and are stored as *LIN16* (16-bit PCM).
      Integer arrays are stored in the closest matching Snack encoding.

    Parameters
    ----------
    arr : array-like
        Audio data.
    sample_rate : int, default 16000
        Sample rate in Hz.

    Returns
    -------
    snack.Sound
    """
    np = _require_numpy()
    from . import Sound

    arr = np.asarray(arr)

    if arr.ndim == 1:
        nchans = 1
        nframes = arr.shape[0]
    elif arr.ndim == 2:
        nchans, nframes = arr.shape
    else:
        raise ValueError(
            f"Expected a 1-D (mono) or 2-D (channels × frames) array; "
            f"got {arr.ndim}-D."
        )

    # Choose Snack encoding and convert to the right byte layout.
    dt = arr.dtype
    if np.issubdtype(dt, np.floating):
        # Floating-point → scale to 16-bit signed PCM (LIN16).
        pcm = np.clip(arr * np.float32(32768.0), -32768, 32767).astype(np.int16)
        encoding = "Lin16"
    elif dt == np.int16:
        pcm = np.asarray(arr, dtype=np.int16)
        encoding = "Lin16"
    elif dt == np.int32:
        pcm = np.asarray(arr, dtype=np.int32)
        encoding = "Lin32"
    elif dt == np.int8:
        pcm = np.asarray(arr, dtype=np.int8)
        encoding = "Lin8"
    elif dt == np.uint8:
        pcm = np.asarray(arr, dtype=np.uint8)
        encoding = "Lin8offset"
    else:
        # Unknown type: cast to float, then scale to int16.
        pcm = np.clip(
            arr.astype(np.float32) * np.float32(32768.0), -32768, 32767
        ).astype(np.int16)
        encoding = "Lin16"

    # Interleave channels: (channels, frames) → (frames, channels) → flat.
    if nchans > 1:
        pcm = np.ascontiguousarray(pcm.T).reshape(-1)
    else:
        pcm = pcm.ravel()

    snd = Sound(sample_rate=sample_rate, channels=nchans, encoding=encoding)
    snd.data(pcm.tobytes())
    return snd


# ---------------------------------------------------------------------------
# librosa compatibility surface
# ---------------------------------------------------------------------------


def to_librosa(sound):
    """Convert a :class:`snack.Sound` to the ``(y, sr)`` tuple that librosa
    functions expect.

    Returns
    -------
    y : numpy.ndarray, float32
        Shape ``(frames,)`` for mono, ``(channels, frames)`` for
        multi-channel audio.  Values are in ``[-1.0, 1.0]``.
    sr : int
        Sample rate in Hz.
    """
    np = _require_numpy()
    y = to_numpy(sound, normalize=True, dtype=np.float32)
    return y, sound.sample_rate


def from_librosa(y, sr):
    """Create a :class:`snack.Sound` from a librosa ``(y, sr)`` pair.

    Parameters
    ----------
    y : numpy.ndarray
        Float audio data, shape ``(frames,)`` for mono or
        ``(channels, frames)`` for multi-channel.  Expected range
        ``[-1.0, 1.0]``.
    sr : int
        Sample rate in Hz.

    Returns
    -------
    snack.Sound
    """
    return from_numpy(y, sample_rate=sr)


def librosa_load(path, sr=None, mono=True, offset=0.0, duration=None):
    """Load an audio file and return it in librosa's ``(y, sr)`` format.

    This is a snack-powered drop-in replacement for ``librosa.load()``.
    It supports all file formats that Snack can read (WAV, AIFF, AU, SND,
    RAW, …) without requiring librosa to be installed.

    Parameters
    ----------
    path : str or path-like
        Path to the audio file.
    sr : int or None, default None
        Target sample rate.  When ``None`` the file's native rate is kept.
        When an integer is given the sound is resampled after loading.
    mono : bool, default True
        When *True*, convert to mono by averaging channels.
    offset : float, default 0.0
        Start reading at this time in seconds.
    duration : float or None, default None
        Read at most this many seconds of audio.

    Returns
    -------
    y : numpy.ndarray, float32
        Shape ``(frames,)`` when *mono* is ``True``, otherwise
        ``(channels, frames)``.
    sr : int
        The sample rate of the returned audio.
    """
    _require_numpy()
    from . import Sound

    snd = Sound()
    snd.read(str(path))

    native_sr = snd.sample_rate
    if offset > 0.0 or duration is not None:
        start = int(offset * native_sr)
        if duration is not None:
            end = min(start + int(duration * native_sr), snd.length)
        else:
            end = snd.length
        # crop(start, end) keeps samples in [start, end-1]
        if start < end:
            snd.crop(start, end - 1)
        else:
            snd.flush()

    if mono and snd.channels > 1:
        snd.convert(channels=1)

    if sr is not None and sr != snd.sample_rate:
        snd.convert(rate=sr)

    y, out_sr = to_librosa(snd)
    snd.destroy()
    return y, out_sr


# ---------------------------------------------------------------------------
# torchaudio / PyTorch compatibility surface
# ---------------------------------------------------------------------------


def to_tensor(sound):
    """Convert a :class:`snack.Sound` to a PyTorch tensor.

    The returned tensor uses torchaudio's canonical layout:
    shape ``(channels, frames)``, dtype ``torch.float32``,
    values in ``[-1.0, 1.0]``.

    Parameters
    ----------
    sound : snack.Sound

    Returns
    -------
    torch.Tensor
        Shape ``(channels, frames)``.

    Raises
    ------
    ImportError
        If PyTorch is not installed.
    """
    np = _require_numpy()
    torch = _require_torch()

    y = to_numpy(sound, normalize=True, dtype=np.float32)
    if y.ndim == 1:
        y = y[np.newaxis, :]  # mono → (1, frames)
    return torch.from_numpy(np.ascontiguousarray(y))


def from_tensor(tensor, sample_rate):
    """Create a :class:`snack.Sound` from a PyTorch tensor.

    Parameters
    ----------
    tensor : torch.Tensor
        Shape ``(channels, frames)`` or ``(frames,)``.  Values should be
        in ``[-1.0, 1.0]``.
    sample_rate : int
        Sample rate in Hz.

    Returns
    -------
    snack.Sound

    Raises
    ------
    ImportError
        If PyTorch is not installed.
    """
    _require_torch()
    np = _require_numpy()

    # Move to CPU and convert to a numpy array without an extra copy where
    # possible.  .detach() is safe even when the tensor requires grad.
    arr = tensor.detach().cpu().numpy()
    return from_numpy(arr, sample_rate=sample_rate)
