"""Tests for snack.interop NumPy conversion functions.

These tests use MockSound objects so they do *not* require the compiled
C extension.  They verify the pure-Python conversion logic in interop.py:
encoding→dtype mapping, normalisation, channel deinterleaving, and round-trips.

Tests that require the real snack extension (integration tests) are marked
with ``@pytest.mark.integration`` and are skipped when the extension is absent.
"""

import sys
import types
import pytest

np = pytest.importorskip("numpy")

# conftest.py loads snack.interop with the correct package context and
# exposes it as `interop` in sys.modules["snack.interop"].
import snack.interop as interop  # noqa: E402  (loaded by conftest.py)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

from _helpers import MockSound, make_lin16_bytes, make_float32_bytes, make_int32_bytes

# Encoding constants (mirror jkAudIO.h)
LIN16 = 1
ALAW = 2
MULAW = 3
LIN8OFFSET = 4
LIN8 = 5
LIN24 = 6
LIN32 = 7
SNACK_FLOAT = 8
SNACK_DOUBLE = 9

to_numpy = interop.to_numpy
from_numpy = interop.from_numpy
to_librosa = interop.to_librosa
from_librosa = interop.from_librosa
to_tensor = interop.to_tensor
from_tensor = interop.from_tensor


# to_numpy — mono
# ---------------------------------------------------------------------------


class TestToNumpyLIN16Mono:
    def test_dtype_is_float32_by_default(self):
        raw = make_lin16_bytes([0, 16384, -16384, 32767, -32768])
        snd = MockSound(raw, LIN16, length=5)
        arr = to_numpy(snd)
        assert arr.dtype == np.float32

    def test_shape_is_1d_for_mono(self):
        raw = make_lin16_bytes([0, 100, -100])
        snd = MockSound(raw, LIN16, length=3)
        arr = to_numpy(snd)
        assert arr.ndim == 1
        assert arr.shape == (3,)

    def test_zero_maps_to_zero(self):
        raw = make_lin16_bytes([0, 0, 0])
        snd = MockSound(raw, LIN16, length=3)
        arr = to_numpy(snd)
        np.testing.assert_array_equal(arr, [0.0, 0.0, 0.0])

    def test_positive_max_maps_to_near_one(self):
        raw = make_lin16_bytes([32767])
        snd = MockSound(raw, LIN16, length=1)
        arr = to_numpy(snd)
        assert abs(arr[0] - 1.0) < 1e-4

    def test_negative_max_maps_to_neg_one(self):
        raw = make_lin16_bytes([-32768])
        snd = MockSound(raw, LIN16, length=1)
        arr = to_numpy(snd)
        assert abs(arr[0] - (-1.0)) < 1e-4

    def test_normalize_false_returns_int16(self):
        raw = make_lin16_bytes([1000, -2000])
        snd = MockSound(raw, LIN16, length=2)
        arr = to_numpy(snd, normalize=False)
        assert arr.dtype == np.int16
        np.testing.assert_array_equal(arr, [1000, -2000])

    def test_explicit_dtype(self):
        raw = make_lin16_bytes([16384])
        snd = MockSound(raw, LIN16, length=1)
        arr = to_numpy(snd, dtype=np.float64)
        assert arr.dtype == np.float64

    def test_empty_sound(self):
        snd = MockSound(b"", LIN16, length=0)
        arr = to_numpy(snd)
        assert arr.shape == (0,)


class TestToNumpyLIN16Stereo:
    def test_shape_is_2d_channels_frames(self):
        # Two frames, stereo: [ch0f0, ch1f0, ch0f1, ch1f1]
        samples = [100, 200, 300, 400]
        raw = make_lin16_bytes(samples)
        snd = MockSound(raw, LIN16, channels=2, length=2)
        arr = to_numpy(snd)
        assert arr.shape == (2, 2)

    def test_channel_deinterleaving(self):
        # ch0: [100, 300], ch1: [200, 400] in interleaved layout
        samples = [100, 200, 300, 400]
        raw = make_lin16_bytes(samples)
        snd = MockSound(raw, LIN16, channels=2, length=2)
        arr = to_numpy(snd, normalize=False)
        np.testing.assert_array_equal(arr[0], [100, 300])
        np.testing.assert_array_equal(arr[1], [200, 400])

    def test_empty_stereo(self):
        snd = MockSound(b"", LIN16, channels=2, length=0)
        arr = to_numpy(snd)
        assert arr.shape == (2, 0)


class TestToNumpyFloat32:
    def test_values_unchanged(self):
        values = [0.5, -0.25, 1.0, -1.0, 0.0]
        raw = make_float32_bytes(values)
        snd = MockSound(raw, SNACK_FLOAT, length=len(values))
        arr = to_numpy(snd)
        np.testing.assert_allclose(arr, values, atol=1e-6)

    def test_normalize_false_same_as_true_for_float(self):
        values = [0.5, -0.5]
        raw = make_float32_bytes(values)
        snd = MockSound(raw, SNACK_FLOAT, length=2)
        arr_norm = to_numpy(snd, normalize=True)
        arr_raw = to_numpy(snd, normalize=False)
        np.testing.assert_allclose(arr_norm, arr_raw, atol=1e-6)


class TestToNumpyLIN32:
    def test_dtype_is_float32_normalized(self):
        raw = make_int32_bytes([0, 2147483647, -2147483648])
        snd = MockSound(raw, LIN32, length=3)
        arr = to_numpy(snd)
        assert arr.dtype == np.float32
        assert abs(arr[1] - 1.0) < 1e-6
        assert abs(arr[2] - (-1.0)) < 1e-6

    def test_normalize_false_returns_int32(self):
        raw = make_int32_bytes([100000, -200000])
        snd = MockSound(raw, LIN32, length=2)
        arr = to_numpy(snd, normalize=False)
        assert arr.dtype == np.int32
        np.testing.assert_array_equal(arr, [100000, -200000])


class TestToNumpyLIN8:
    def test_signed_int8(self):
        raw = bytes([0, 127, 128])  # 0, 127, -128 when signed
        snd = MockSound(raw, LIN8, length=3)
        arr = to_numpy(snd, normalize=False)
        assert arr.dtype == np.int8
        np.testing.assert_array_equal(arr, [0, 127, -128])

    def test_normalized_range(self):
        raw = bytes([0, 127, 128])
        snd = MockSound(raw, LIN8, length=3)
        arr = to_numpy(snd)
        assert arr[0] == pytest.approx(0.0, abs=1e-3)
        assert arr[1] == pytest.approx(127.0 / 128.0, abs=1e-3)
        assert arr[2] == pytest.approx(-1.0, abs=1e-3)


class TestToNumpyLIN8OFFSET:
    def test_128_maps_to_zero(self):
        raw = bytes([128])
        snd = MockSound(raw, LIN8OFFSET, length=1)
        arr = to_numpy(snd)
        assert arr[0] == pytest.approx(0.0, abs=1e-3)

    def test_0_maps_to_neg_one(self):
        raw = bytes([0])
        snd = MockSound(raw, LIN8OFFSET, length=1)
        arr = to_numpy(snd)
        assert arr[0] == pytest.approx(-1.0, abs=1e-3)

    def test_255_maps_to_near_pos_one(self):
        raw = bytes([255])
        snd = MockSound(raw, LIN8OFFSET, length=1)
        arr = to_numpy(snd)
        assert arr[0] == pytest.approx(127.0 / 128.0, abs=1e-3)


class TestToNumpyUnsupported:
    def test_raises_for_unknown_encoding(self):
        snd = MockSound(b"\x00" * 4, encoding=99, length=2)
        with pytest.raises(ValueError, match="Unsupported Snack encoding"):
            to_numpy(snd)


# ---------------------------------------------------------------------------
# from_numpy — mono
# ---------------------------------------------------------------------------


class TestFromNumpyMono:
    """from_numpy uses snack.Sound internally; we test via a patched module.

    conftest.py put a stub snack module in sys.modules["snack"].  We patch
    its ``Sound`` attribute so from_numpy picks up our MockSound factory.
    """

    def _from_numpy_patched(self, arr, sample_rate=16000):
        """Call from_numpy with MockSound injected as the Sound constructor."""
        created = []
        snack_stub = sys.modules["snack"]

        class CaptureSoundFactory:
            def __init__(self, sample_rate, channels, encoding):
                self._snd = MockSound(
                    b"",
                    {"Lin16": LIN16, "Lin32": LIN32, "Lin8": LIN8,
                     "Lin8offset": LIN8OFFSET}.get(encoding, LIN16),
                    sample_rate=sample_rate,
                    channels=channels,
                    length=0,
                )
                created.append(self._snd)

            def data(self, d=None):
                return self._snd.data(d)

            @property
            def sample_rate(self):
                return self._snd.sample_rate

            @property
            def channels(self):
                return self._snd.channels

            @property
            def length(self):
                return self._snd.length

            @property
            def encoding(self):
                return self._snd.encoding

        factory_instance = None

        def fake_sound(*args, **kwargs):
            fs = CaptureSoundFactory(**kwargs)
            nonlocal factory_instance
            factory_instance = fs
            return fs

        # Patch the Sound attribute on the stub snack module.
        orig_sound = getattr(snack_stub, "Sound", None)
        snack_stub.Sound = fake_sound
        try:
            result = interop.from_numpy(arr, sample_rate=sample_rate)
        finally:
            snack_stub.Sound = orig_sound

        return result, factory_instance

    def test_float32_stored_as_lin16(self):
        arr = np.array([0.5, -0.5, 1.0, -1.0], dtype=np.float32)
        snd, captured = self._from_numpy_patched(arr)
        # Check raw bytes can be decoded back to int16
        assert captured is not None
        raw = captured.data()
        ints = np.frombuffer(raw, dtype=np.int16)
        assert ints[0] == pytest.approx(0.5 * 32768, abs=2)
        assert ints[1] == pytest.approx(-0.5 * 32768, abs=2)
        assert ints[2] <= 32767  # clipped
        assert ints[3] >= -32768  # clipped

    def test_int16_stored_as_lin16(self):
        arr = np.array([1000, -2000, 0], dtype=np.int16)
        snd, captured = self._from_numpy_patched(arr)
        raw = captured.data()
        ints = np.frombuffer(raw, dtype=np.int16)
        np.testing.assert_array_equal(ints, arr)

    def test_wrong_ndim_raises(self):
        arr = np.zeros((2, 2, 2), dtype=np.float32)
        with pytest.raises(ValueError, match="1-D"):
            interop.from_numpy(arr)

    def test_sample_rate_passed_through(self):
        arr = np.array([0.0, 0.1], dtype=np.float32)
        snd, captured = self._from_numpy_patched(arr, sample_rate=44100)
        assert captured.sample_rate == 44100

    def test_stereo_channels_set(self):
        arr = np.array([[0.1, 0.2], [-0.1, -0.2]], dtype=np.float32)  # (2, 2)
        snd, captured = self._from_numpy_patched(arr)
        assert captured.channels == 2

    def test_stereo_interleaving(self):
        # ch0=[1000, 3000], ch1=[2000, 4000]
        arr = np.array([[1000, 3000], [2000, 4000]], dtype=np.int16)
        snd, captured = self._from_numpy_patched(arr)
        raw = captured.data()
        ints = np.frombuffer(raw, dtype=np.int16)
        # Expected interleaved: [1000, 2000, 3000, 4000]
        np.testing.assert_array_equal(ints, [1000, 2000, 3000, 4000])


# ---------------------------------------------------------------------------
# Conversion round-trip via MockSound (no C extension needed)
# ---------------------------------------------------------------------------


class TestRoundTripLIN16:
    """Test that to_numpy ∘ from_numpy is a near-identity for float32 input."""

    def test_mono_round_trip(self):
        # Build a MockSound from known int16 bytes, convert to numpy, check values.
        original = np.array([0.5, -0.25, 0.75], dtype=np.float32)
        # Encode to int16
        pcm = np.clip(original * 32768.0, -32768, 32767).astype(np.int16)
        raw = pcm.tobytes()
        snd = MockSound(raw, LIN16, length=3)
        recovered = to_numpy(snd)
        np.testing.assert_allclose(recovered, original, atol=1.0 / 32768)

    def test_stereo_round_trip(self):
        # (2, 3) float32 → int16 interleaved → MockSound → to_numpy
        original = np.array([[0.1, 0.2, 0.3], [-0.1, -0.2, -0.3]],
                             dtype=np.float32)
        pcm = np.clip(original * 32768.0, -32768, 32767).astype(np.int16)
        # interleave: (2,3) → (3,2) → flat
        interleaved = np.ascontiguousarray(pcm.T).reshape(-1)
        raw = interleaved.tobytes()
        snd = MockSound(raw, LIN16, channels=2, length=3)
        recovered = to_numpy(snd)
        assert recovered.shape == (2, 3)
        np.testing.assert_allclose(recovered, original, atol=1.0 / 32768)


# ---------------------------------------------------------------------------
# NumPy requirement guard
# ---------------------------------------------------------------------------


class TestNumpyRequired:
    def test_raises_import_error_without_numpy(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "numpy", None)
        with pytest.raises(ImportError, match="NumPy"):
            snd = MockSound(b"\x00\x00", LIN16, length=1)
            interop.to_numpy(snd)
