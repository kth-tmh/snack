"""
Tests for snack.iir_filter.

These tests exercise the pure Python/NumPy fallback implementation directly
(no C extension required) and, when the C extension is available, also
verify that the C binding produces identical results.
"""

import math
import unittest

import numpy as np

from snack.iir import _iir_filter_numpy, iir_filter


def _allclose(a, b, atol=1e-5):
    return np.allclose(np.asarray(a, np.float32), np.asarray(b, np.float32), atol=atol)


class TestIirFilterPassthrough(unittest.TestCase):
    """b=[1], a=[1] must return input unchanged (identity filter)."""

    def test_mono_identity(self):
        x = np.array([1.0, 2.0, 3.0, -1.0, 0.5], dtype=np.float32)
        y = iir_filter(x, b=[1.0], a=[1.0])
        self.assertTrue(_allclose(x, y))

    def test_multi_channel_identity(self):
        # 2 channels, 4 frames: [ch0f0, ch1f0, ch0f1, ch1f1, ...]
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], dtype=np.float32)
        y = iir_filter(x, b=[1.0], a=[1.0], channels=2)
        self.assertTrue(_allclose(x, y))

    def test_zero_input(self):
        x = np.zeros(10, dtype=np.float32)
        y = iir_filter(x, b=[1.0, 0.5], a=[1.0])
        self.assertTrue(_allclose(x, y))


class TestIirFilterFIR(unittest.TestCase):
    """Pure FIR (no feedback): convolution with b coefficients."""

    def test_moving_average(self):
        # 3-tap moving average: y[n] = (x[n] + x[n-1] + x[n-2]) / 3
        b = [1.0 / 3, 1.0 / 3, 1.0 / 3]
        a = [1.0]
        x = np.array([3.0, 3.0, 3.0, 3.0, 3.0], dtype=np.float32)
        y = iir_filter(x, b=b, a=a)
        # After the 3rd sample the average should be exactly 3.0
        self.assertAlmostEqual(float(y[4]), 3.0, places=5)

    def test_delay_one(self):
        # b=[0, 1]: y[n] = x[n-1], so output is x shifted right by 1
        b = [0.0, 1.0]
        x = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
        y = iir_filter(x, b=b)
        expected = np.array([0.0, 1.0, 2.0, 3.0], dtype=np.float32)
        self.assertTrue(_allclose(y, expected))


class TestIirFilterIIR(unittest.TestCase):
    """IIR (with feedback) correctness tests."""

    def test_first_order_lowpass(self):
        # y[n] = alpha * x[n] + (1 - alpha) * y[n-1]
        # In standard form: a[0]=1, a[1]=-(1-alpha), b[0]=alpha
        alpha = 0.2
        b = [alpha]
        a = [1.0, -(1.0 - alpha)]
        # Step response: should converge to 1.0
        x = np.ones(50, dtype=np.float32)
        y = iir_filter(x, b=b, a=a)
        self.assertAlmostEqual(float(y[-1]), 1.0, places=4)

    def test_known_values(self):
        # Hand-compute a 2-tap IIR:
        # a=[1, -0.5], b=[1]
        # y[0] = x[0] / 1             = 1.0
        # y[1] = (x[1] + 0.5*y[0]) / 1 = 1.5
        # y[2] = (x[2] + 0.5*y[1]) / 1 = 1.75
        b = [1.0]
        a = [1.0, -0.5]
        x = np.ones(3, dtype=np.float32)
        y = iir_filter(x, b=b, a=a)
        self.assertAlmostEqual(float(y[0]), 1.0, places=5)
        self.assertAlmostEqual(float(y[1]), 1.5, places=5)
        self.assertAlmostEqual(float(y[2]), 1.75, places=5)

    def test_a0_scaling(self):
        # Scaling a by 2 should halve the output
        b = [1.0]
        x = np.array([1.0, 1.0, 1.0], dtype=np.float32)
        y1 = iir_filter(x, b=b, a=[1.0])
        y2 = iir_filter(x, b=b, a=[2.0])
        self.assertTrue(_allclose(y1, y2 * 2.0))


class TestIirFilterDeterminism(unittest.TestCase):
    """Default mode (deterministic=True) must produce identical output on repeated calls."""

    def test_repeated_calls_identical(self):
        b = [0.3, 0.5, 0.2]
        a = [1.0, -0.4]
        x = np.random.default_rng(0).standard_normal(100).astype(np.float32)
        y1 = iir_filter(x, b=b, a=a)
        y2 = iir_filter(x, b=b, a=a)
        np.testing.assert_array_equal(y1, y2)

    def test_seed_reproducibility(self):
        b = [1.0]
        a = [1.0]
        x = np.ones(20, dtype=np.float32)
        # With explicit seed and noise, same seed → same output
        y1 = iir_filter(x, b=b, a=a, noise=0.01, dither=0.01, seed=42, deterministic=False)
        y2 = iir_filter(x, b=b, a=a, noise=0.01, dither=0.01, seed=42, deterministic=False)
        np.testing.assert_array_equal(y1, y2)

    def test_different_seeds_differ(self):
        b = [1.0]
        a = [1.0]
        x = np.ones(20, dtype=np.float32)
        y1 = iir_filter(x, b=b, a=a, noise=0.1, seed=1, deterministic=False)
        y2 = iir_filter(x, b=b, a=a, noise=0.1, seed=2, deterministic=False)
        self.assertFalse(np.array_equal(y1, y2))

    def test_deterministic_overrides_noise(self):
        b = [1.0]
        a = [1.0]
        x = np.ones(20, dtype=np.float32)
        # Even with large noise, deterministic=True must suppress it
        y1 = iir_filter(x, b=b, a=a, noise=10.0, dither=10.0, deterministic=True)
        y2 = iir_filter(x, b=b, a=a, noise=0.0, dither=0.0)
        np.testing.assert_array_equal(y1, y2)


class TestIirFilterMetadata(unittest.TestCase):
    """return_metadata=True returns (y, dict) with expected keys."""

    def test_metadata_structure(self):
        x = np.ones(5, dtype=np.float32)
        y, meta = iir_filter(x, b=[1.0], a=[1.0], return_metadata=True)
        self.assertIsInstance(y, np.ndarray)
        self.assertIsInstance(meta, dict)
        for key in ("algorithm", "parameters", "version", "hash"):
            self.assertIn(key, meta)
        self.assertEqual(meta["algorithm"], "iir")
        self.assertTrue(meta["hash"].startswith("sha256:"))

    def test_metadata_hash_changes_with_input(self):
        y1, m1 = iir_filter(np.ones(5, dtype=np.float32), b=[1.0], return_metadata=True)
        y2, m2 = iir_filter(np.zeros(5, dtype=np.float32), b=[1.0], return_metadata=True)
        self.assertNotEqual(m1["hash"], m2["hash"])


class TestIirFilterNumpyFallback(unittest.TestCase):
    """Directly test the pure NumPy fallback to ensure it matches known values."""

    def test_identity(self):
        x = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        y = _iir_filter_numpy(x, [1.0], [1.0])
        self.assertTrue(_allclose(x, y))

    def test_known_values(self):
        b = [1.0]
        a = [1.0, -0.5]
        x = np.ones(3, dtype=np.float32)
        y = _iir_filter_numpy(x, b, a)
        self.assertAlmostEqual(float(y[0]), 1.0, places=5)
        self.assertAlmostEqual(float(y[1]), 1.5, places=5)
        self.assertAlmostEqual(float(y[2]), 1.75, places=5)


class TestIirFilterCBinding(unittest.TestCase):
    """Verify C binding matches pure NumPy fallback when the extension is present."""

    @classmethod
    def setUpClass(cls):
        try:
            import snack._snack as _c
            cls._c = _c
            cls.have_c = hasattr(_c, "iir_filter")
        except ImportError:
            cls.have_c = False

    def _skip_if_no_c(self):
        if not self.have_c:
            self.skipTest("C extension iir_filter not available")

    def test_c_matches_numpy_identity(self):
        self._skip_if_no_c()
        b = [1.0]
        a = [1.0]
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float32)
        ref = _iir_filter_numpy(x, b, a)
        raw = self._c.iir_filter(x, b, a)
        got = np.frombuffer(bytes(raw), dtype=np.float32)
        np.testing.assert_allclose(got, ref, atol=1e-6)

    def test_c_matches_numpy_first_order(self):
        self._skip_if_no_c()
        alpha = 0.3
        b = [alpha]
        a = [1.0, -(1.0 - alpha)]
        rng = np.random.default_rng(7)
        x = rng.standard_normal(50).astype(np.float32)
        ref = _iir_filter_numpy(x, b, a)
        raw = self._c.iir_filter(x, b, a)
        got = np.frombuffer(bytes(raw), dtype=np.float32)
        np.testing.assert_allclose(got, ref, atol=1e-5)

    def test_c_deterministic_no_noise(self):
        self._skip_if_no_c()
        b, a = [0.5, 0.3], [1.0, -0.2]
        x = np.ones(10, dtype=np.float32)
        raw1 = self._c.iir_filter(x, b, a, 1, 0.0, 0.0, 1)
        raw2 = self._c.iir_filter(x, b, a, 1, 0.0, 0.0, 1)
        np.testing.assert_array_equal(
            np.frombuffer(bytes(raw1), dtype=np.float32),
            np.frombuffer(bytes(raw2), dtype=np.float32),
        )


if __name__ == "__main__":
    unittest.main()
