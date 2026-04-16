"""Shared test fixtures and mock objects for snack interop tests.

The MockSound class mimics the duck-type interface that interop.py uses
so that the conversion logic can be tested without requiring the compiled
C extension.
"""

import struct


class MockSound:
    """A minimal duck-type replacement for snack.Sound used in unit tests.

    Only the attributes and methods consumed by snack.interop are implemented.
    """

    def __init__(self, raw_bytes, encoding, sample_rate=16000, channels=1,
                 length=None):
        self._data = raw_bytes
        self.encoding = encoding
        self.sample_rate = sample_rate
        self.channels = channels
        if length is not None:
            self.length = length
        else:
            # Infer length from encoding and raw byte length.
            bytes_per_sample = _bytes_per_sample(encoding)
            if bytes_per_sample:
                self.length = len(raw_bytes) // (bytes_per_sample * channels)
            else:
                self.length = 0

    def data(self, d=None):
        if d is None:
            return self._data
        self._data = bytes(d)
        # Update length based on encoding
        bytes_per_sample = _bytes_per_sample(self.encoding)
        if bytes_per_sample:
            self.length = len(self._data) // (bytes_per_sample * self.channels)

    def destroy(self):
        pass

    def convert(self, **kw):
        """Stub – real conversion happens in the C extension."""
        pass

    def flush(self):
        self._data = b""
        self.length = 0

    def crop(self, start, end):
        pass


def _bytes_per_sample(encoding):
    """Return bytes per single-channel sample for known encoding ids."""
    return {
        1: 2,   # LIN16
        2: 1,   # ALAW
        3: 1,   # MULAW
        4: 1,   # LIN8OFFSET
        5: 1,   # LIN8
        6: 3,   # LIN24
        7: 4,   # LIN32
        8: 4,   # SNACK_FLOAT
        9: 8,   # SNACK_DOUBLE
    }.get(encoding)


def make_lin16_bytes(samples):
    """Pack a list of int16 values into little-endian bytes."""
    return struct.pack(f"<{len(samples)}h", *samples)


def make_float32_bytes(samples):
    """Pack a list of float32 values into bytes."""
    return struct.pack(f"<{len(samples)}f", *samples)


def make_int32_bytes(samples):
    """Pack a list of int32 values into bytes."""
    return struct.pack(f"<{len(samples)}i", *samples)
