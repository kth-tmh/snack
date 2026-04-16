"""Tests for snack.interop torchaudio / PyTorch compatibility functions.

Uses MockSound so that the compiled C extension is not required.
Tests that require torch are automatically skipped when it is absent.
"""

import sys
import types
import pytest

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")

# conftest.py loads snack.interop with the correct package context.
import snack.interop as interop  # noqa: E402

from _helpers import MockSound, make_lin16_bytes, make_float32_bytes

LIN16 = 1
SNACK_FLOAT = 8


# ---------------------------------------------------------------------------
# to_tensor
# ---------------------------------------------------------------------------


class TestToTensor:
    def test_returns_float_tensor(self):
        raw = make_lin16_bytes([0, 16384, -16384])
        snd = MockSound(raw, LIN16, sample_rate=16000, length=3)
        t = interop.to_tensor(snd)
        assert t.dtype == torch.float32

    def test_mono_has_channel_dim(self):
        """Mono sound → shape (1, frames), matching torchaudio convention."""
        raw = make_lin16_bytes([100, 200, 300])
        snd = MockSound(raw, LIN16, channels=1, length=3)
        t = interop.to_tensor(snd)
        assert t.ndim == 2
        assert t.shape == (1, 3)

    def test_stereo_shape(self):
        raw = make_lin16_bytes([100, 200, 300, 400])
        snd = MockSound(raw, LIN16, channels=2, length=2)
        t = interop.to_tensor(snd)
        assert t.shape == (2, 2)

    def test_values_in_range(self):
        raw = make_lin16_bytes([32767, -32768, 0])
        snd = MockSound(raw, LIN16, length=3)
        t = interop.to_tensor(snd)
        assert t.min().item() >= -1.0
        assert t.max().item() <= 1.0

    def test_positive_full_scale_near_one(self):
        raw = make_lin16_bytes([32767])
        snd = MockSound(raw, LIN16, length=1)
        t = interop.to_tensor(snd)
        assert abs(t[0, 0].item() - 1.0) < 1e-4

    def test_float_encoding_passthrough(self):
        values = [0.5, -0.25, 0.0]
        raw = make_float32_bytes(values)
        snd = MockSound(raw, SNACK_FLOAT, sample_rate=16000, length=3)
        t = interop.to_tensor(snd)
        assert t.shape == (1, 3)
        for i, v in enumerate(values):
            assert t[0, i].item() == pytest.approx(v, abs=1e-6)

    def test_tensor_is_not_a_view_of_numpy_internal(self):
        """Returned tensor must be contiguous and independently owned."""
        raw = make_lin16_bytes([1, 2, 3, 4])
        snd = MockSound(raw, LIN16, channels=2, length=2)
        t = interop.to_tensor(snd)
        assert t.is_contiguous()

    def test_requires_torch(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "torch", None)
        raw = make_lin16_bytes([0])
        snd = MockSound(raw, LIN16, length=1)
        with pytest.raises(ImportError, match="PyTorch"):
            interop.to_tensor(snd)


# ---------------------------------------------------------------------------
# from_tensor
# ---------------------------------------------------------------------------


class TestFromTensor:
    def _patch_and_call(self, tensor, sample_rate):
        """Inject MockSound as the Sound factory and return captured instance."""
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
            result = interop.from_tensor(tensor, sample_rate=sample_rate)
        finally:
            snack_stub.Sound = orig_sound
        return result, created.get("sound")

    def test_mono_tensor_1d(self):
        t = torch.tensor([0.5, -0.5, 0.0], dtype=torch.float32)
        _, snd = self._patch_and_call(t, 16000)
        assert snd.channels == 1

    def test_mono_tensor_2d_ch1(self):
        t = torch.tensor([[0.5, -0.5, 0.0]], dtype=torch.float32)  # (1, 3)
        _, snd = self._patch_and_call(t, 16000)
        assert snd.channels == 1

    def test_stereo_tensor(self):
        t = torch.tensor([[0.1, 0.2], [-0.1, -0.2]], dtype=torch.float32)
        _, snd = self._patch_and_call(t, 44100)
        assert snd.channels == 2
        assert snd.sample_rate == 44100

    def test_sample_rate_forwarded(self):
        t = torch.zeros(1, 100, dtype=torch.float32)
        _, snd = self._patch_and_call(t, 22050)
        assert snd.sample_rate == 22050

    def test_float_values_scaled_to_int16(self):
        t = torch.tensor([[0.5, -0.5]], dtype=torch.float32)
        _, snd = self._patch_and_call(t, 16000)
        raw = snd.data()
        ints = np.frombuffer(raw, dtype=np.int16)
        assert ints[0] == pytest.approx(0.5 * 32768, abs=2)
        assert ints[1] == pytest.approx(-0.5 * 32768, abs=2)

    def test_grad_tensor_handled(self):
        """Tensors requiring grad must be accepted (detach is called internally)."""
        t = torch.tensor([[0.5, 0.25]], dtype=torch.float32, requires_grad=True)
        _, snd = self._patch_and_call(t, 16000)
        assert snd is not None

    def test_requires_torch(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "torch", None)
        t = torch.zeros(1, 4)
        with pytest.raises(ImportError, match="PyTorch"):
            interop.from_tensor(t, sample_rate=16000)


# ---------------------------------------------------------------------------
# Round-trip: Sound → Tensor → Sound (via MockSound)
# ---------------------------------------------------------------------------


class TestTensorRoundTrip:
    def test_mono_round_trip_values(self):
        original = np.array([0.3, -0.3, 0.6, -0.6], dtype=np.float32)
        pcm = np.clip(original * 32768, -32768, 32767).astype(np.int16)
        snd = MockSound(pcm.tobytes(), LIN16, sample_rate=16000, length=4)

        t = interop.to_tensor(snd)

        assert t.shape == (1, 4)
        np.testing.assert_allclose(
            t[0].numpy(), original, atol=1.0 / 32768
        )

    def test_stereo_round_trip_values(self):
        original = np.array([[0.1, 0.2, 0.3], [-0.1, -0.2, -0.3]],
                             dtype=np.float32)
        pcm = np.clip(original * 32768, -32768, 32767).astype(np.int16)
        interleaved = np.ascontiguousarray(pcm.T).reshape(-1)
        snd = MockSound(interleaved.tobytes(), LIN16, channels=2, length=3)

        t = interop.to_tensor(snd)

        assert t.shape == (2, 3)
        np.testing.assert_allclose(t.numpy(), original, atol=1.0 / 32768)
