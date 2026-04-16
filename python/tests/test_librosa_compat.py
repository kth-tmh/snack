"""Tests for snack.interop librosa compatibility functions.

Uses MockSound so that the compiled C extension is not required.
Integration tests that verify actual audio file loading are skipped
when the snack extension or librosa are absent.
"""

import sys
import types
import pytest

np = pytest.importorskip("numpy")

# conftest.py loads snack.interop with the correct package context.
import snack.interop as interop  # noqa: E402

from _helpers import MockSound, make_lin16_bytes, make_float32_bytes

LIN16 = 1
SNACK_FLOAT = 8


# ---------------------------------------------------------------------------
# to_librosa
# ---------------------------------------------------------------------------


class TestToLibrosa:
    def test_returns_tuple_y_sr(self):
        raw = make_lin16_bytes([0, 16384, -16384])
        snd = MockSound(raw, LIN16, sample_rate=22050, length=3)
        result = interop.to_librosa(snd)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_y_is_float32(self):
        raw = make_lin16_bytes([0, 16384, -16384])
        snd = MockSound(raw, LIN16, sample_rate=16000, length=3)
        y, sr = interop.to_librosa(snd)
        assert y.dtype == np.float32

    def test_sr_matches_sound(self):
        raw = make_lin16_bytes([0])
        snd = MockSound(raw, LIN16, sample_rate=44100, length=1)
        y, sr = interop.to_librosa(snd)
        assert sr == 44100

    def test_values_in_range(self):
        raw = make_lin16_bytes([0, 32767, -32768, 16384])
        snd = MockSound(raw, LIN16, sample_rate=16000, length=4)
        y, sr = interop.to_librosa(snd)
        assert y.min() >= -1.0
        assert y.max() <= 1.0

    def test_mono_shape_is_1d(self):
        raw = make_lin16_bytes([1, 2, 3, 4])
        snd = MockSound(raw, LIN16, channels=1, length=4)
        y, sr = interop.to_librosa(snd)
        assert y.ndim == 1

    def test_stereo_shape_is_2d(self):
        raw = make_lin16_bytes([100, 200, 300, 400])
        snd = MockSound(raw, LIN16, channels=2, length=2)
        y, sr = interop.to_librosa(snd)
        assert y.shape == (2, 2)

    def test_float_encoding_passthrough(self):
        values = [0.5, -0.25, 0.0, 1.0]
        raw = make_float32_bytes(values)
        snd = MockSound(raw, SNACK_FLOAT, sample_rate=16000, length=4)
        y, sr = interop.to_librosa(snd)
        np.testing.assert_allclose(y, values, atol=1e-6)


# ---------------------------------------------------------------------------
# from_librosa
# ---------------------------------------------------------------------------


class TestFromLibrosa:
    """from_librosa delegates to from_numpy; verify the pass-through."""

    def _patch_and_call(self, y, sr):
        """Inject a MockSound factory so we can inspect what was created."""
        created = {}
        snack_stub = sys.modules["snack"]

        class FakeSound:
            def __init__(self, sample_rate, channels, encoding):
                self._sr = sample_rate
                self._ch = channels
                self._enc = encoding
                self._data = b""
                created["sound"] = self

            @property
            def sample_rate(self):
                return self._sr

            @property
            def channels(self):
                return self._ch

            @property
            def encoding(self):
                return self._enc

            @property
            def length(self):
                bps = {"Lin16": 2, "Lin32": 4, "Lin8": 1, "Lin8offset": 1}.get(
                    self._enc, 2
                )
                return len(self._data) // (bps * self._ch)

            def data(self, d=None):
                if d is None:
                    return self._data
                self._data = bytes(d)

        orig_sound = getattr(snack_stub, "Sound", None)
        snack_stub.Sound = FakeSound
        try:
            result = interop.from_librosa(y, sr)
        finally:
            snack_stub.Sound = orig_sound
        return result, created.get("sound")

    def test_sample_rate_forwarded(self):
        y = np.array([0.1, -0.1], dtype=np.float32)
        _, snd = self._patch_and_call(y, sr=22050)
        assert snd.sample_rate == 22050

    def test_mono_float_to_lin16(self):
        y = np.array([0.5, -0.5], dtype=np.float32)
        _, snd = self._patch_and_call(y, sr=16000)
        assert snd.channels == 1
        raw = snd.data()
        ints = np.frombuffer(raw, dtype=np.int16)
        assert ints[0] == pytest.approx(0.5 * 32768, abs=2)

    def test_stereo_channels_correct(self):
        y = np.array([[0.1, 0.2], [-0.1, -0.2]], dtype=np.float32)
        _, snd = self._patch_and_call(y, sr=44100)
        assert snd.channels == 2

    def test_librosa_round_trip(self):
        """to_librosa ∘ from_librosa should be near-identity."""
        # Build source via MockSound
        original = np.array([0.3, -0.3, 0.6, -0.6], dtype=np.float32)
        pcm = np.clip(original * 32768, -32768, 32767).astype(np.int16)
        snd = MockSound(pcm.tobytes(), LIN16, sample_rate=16000, length=4)

        # to_librosa → (y, sr)
        y, sr = interop.to_librosa(snd)
        # Re-encode into a new MockSound via from_librosa
        _, captured = self._patch_and_call(y, sr)
        raw = captured.data()
        ints = np.frombuffer(raw, dtype=np.int16)
        recovered = ints.astype(np.float32) / 32768.0
        np.testing.assert_allclose(recovered, original, atol=1.0 / 32768)


# ---------------------------------------------------------------------------
# librosa_load  (requires real snack + a WAV file → integration only)
# ---------------------------------------------------------------------------


def _try_import_snack():
    try:
        import snack._snack  # Only succeeds if the compiled C extension is installed
        return True
    except ImportError:
        return False


# Integration test class – only collected when snack is importable.
if _try_import_snack():
    import snack as _snack

    class TestLibrosaLoadIntegration:
        """Real file loading tests (require compiled snack extension)."""

        @pytest.fixture()
        def wav_path(self, tmp_path):
            """Write a minimal valid WAV file for testing."""
            import wave
            import array
            p = tmp_path / "test.wav"
            samples = [int(0.5 * 32767 * ((-1) ** i)) for i in range(1600)]
            with wave.open(str(p), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(array.array("h", samples).tobytes())
            return str(p)

        def test_returns_y_sr_tuple(self, wav_path):
            y, sr = _snack.librosa_load(wav_path)
            assert isinstance(y, np.ndarray)
            assert isinstance(sr, int)

        def test_sr_matches_file(self, wav_path):
            y, sr = _snack.librosa_load(wav_path)
            assert sr == 16000

        def test_y_is_float32(self, wav_path):
            y, sr = _snack.librosa_load(wav_path)
            assert y.dtype == np.float32

        def test_mono_output_is_1d(self, wav_path):
            y, sr = _snack.librosa_load(wav_path, mono=True)
            assert y.ndim == 1

        def test_values_in_range(self, wav_path):
            y, sr = _snack.librosa_load(wav_path)
            assert y.min() >= -1.0
            assert y.max() <= 1.0

        def test_resample(self, wav_path):
            y, sr = _snack.librosa_load(wav_path, sr=8000)
            assert sr == 8000
            # Duration should be preserved (within ±1 sample at 8 kHz)
            expected_frames = 800  # 1600 @ 16 kHz → 800 @ 8 kHz
            assert abs(len(y) - expected_frames) <= 2
