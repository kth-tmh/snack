# snack-sound

A Python C extension for the [Snack Sound Toolkit](http://www.speech.kth.se/snack/)
(v2.2) developed at KTH — Royal Institute of Technology, Sweden.

Snack provides high-level audio objects for playing, recording, and analysing
sound. This package exposes Snack's non-graphical functionality directly to
Python without requiring Tcl/Tk or Tkinter at runtime.

## Requirements

* Python ≥ 3.8
* A Tcl installation at build time (`tcl-dev` on Debian/Ubuntu, `tcl-tk` via
  Homebrew on macOS)
* ALSA (`libasound2-dev`) on Linux for audio I/O

## Installation

```
pip install snack-sound
```

With optional ecosystem extras:

```
pip install "snack-sound[numpy]"    # NumPy interop only
pip install "snack-sound[librosa]"  # librosa integration
pip install "snack-sound[torch]"    # torchaudio / PyTorch integration
pip install "snack-sound[all]"      # everything
```

Or build from source:

```
cd python/
pip install .
```

---

## Quick start (modern API)

```python
from snack import Sound

s = Sound()
s.read("hello.wav")
print(s.info())       # {length, sample_rate, max, min, encoding, channels, …}
s.play(blocking=True)
s.write("copy.wav")
```

### Tone generation

```python
from snack import Sound, Filter

s = Sound()
filt = Filter("generator", 440, 30000, 0.0, "sine", 8000)
s.play(filter=filt, blocking=True)
```

### Signal analysis

```python
from snack import Sound

s = Sound()
s.read("speech.wav")
pitch = s.pitch()          # list of F0 values per frame
power = s.power()          # RMS power per frame
formants = s.formant()     # list of (F1, F2, F3, …) per frame
spectrum = s.power_spectrum()
```

---

## NumPy interoperability

`snack` can exchange audio with NumPy without going through intermediate files.

### Canonical data contract

| Property      | Value                                              |
|---------------|----------------------------------------------------|
| Shape         | `(frames,)` for mono; `(channels, frames)` for multi-channel |
| dtype         | `numpy.float32`                                    |
| Range         | `[-1.0, 1.0]`                                      |
| Channel order | left-first (matches librosa and torchaudio)        |

### Sound → NumPy

```python
import snack
import numpy as np

snd = snack.Sound()
snd.read("speech.wav")

# Returns float32 array in [-1, 1], shape (frames,) for mono
y = snack.to_numpy(snd)

# Keep raw integer values (no normalisation)
y_raw = snack.to_numpy(snd, normalize=False)   # dtype=int16 for Lin16 sounds

# Request a specific dtype
y64 = snack.to_numpy(snd, dtype=np.float64)
```

### NumPy → Sound

```python
# float32 in [-1, 1] → stored as Lin16 (16-bit PCM)
arr = np.array([0.0, 0.5, -0.5, 1.0], dtype=np.float32)
snd = snack.from_numpy(arr, sample_rate=16000)
snd.play(blocking=True)

# Stereo: shape (channels, frames)
stereo = np.random.uniform(-0.1, 0.1, (2, 44100)).astype(np.float32)
snd2 = snack.from_numpy(stereo, sample_rate=44100)
```

### Encoding → NumPy dtype mapping

| Snack encoding  | numpy dtype | divisor to reach ±1.0 |
|-----------------|-------------|------------------------|
| LIN16           | int16       | 32 768                 |
| LIN32           | int32       | 2 147 483 648          |
| SNACK_FLOAT     | float32     | 1.0 (already in range) |
| SNACK_DOUBLE    | float64     | 1.0 (already in range) |
| LIN8            | int8        | 128                    |
| LIN8OFFSET      | uint8       | 128 (centred at 128)   |
| LIN24           | int32*      | 8 388 608 (*promoted via Snack) |
| ALAW / MULAW    | —           | decoded to LIN16 first |

---

## librosa integration

`snack` provides a drop-in replacement for `librosa.load()` and helpers to
convert between Snack Sound objects and librosa's `(y, sr)` format.
**librosa itself is not required** for these helpers — only NumPy is.

### Load an audio file (librosa-compatible)

```python
import snack

# Same signature and return type as librosa.load()
y, sr = snack.librosa_load("speech.wav")             # mono float32, native rate
y, sr = snack.librosa_load("speech.wav", sr=16000)   # resample to 16 kHz
y, sr = snack.librosa_load("speech.wav", mono=False) # preserve stereo

# Offset and duration (in seconds)
y, sr = snack.librosa_load("speech.wav", offset=1.0, duration=5.0)
```

### Sound ↔ librosa

```python
import snack

snd = snack.Sound()
snd.read("speech.wav")

# Export: Sound → (y, sr) compatible with librosa functions
y, sr = snack.to_librosa(snd)

# Import: (y, sr) back to Sound
snd2 = snack.from_librosa(y, sr)
snd2.play(blocking=True)
```

### Use with existing librosa code

```python
import snack
import librosa

# Load via snack (supports more file formats)
y, sr = snack.librosa_load("speech.wav")

# Pass to any librosa function unchanged
mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
chroma = librosa.feature.chroma_stft(y=y, sr=sr)
```

---

## torchaudio / PyTorch integration

`snack` can exchange audio with PyTorch tensors using torchaudio's canonical
`(channels, frames)` layout.  **PyTorch is not required** unless you call these
functions.

### Sound → Tensor

```python
import snack

snd = snack.Sound()
snd.read("speech.wav")

# Returns float32 tensor of shape (channels, frames) in [-1, 1]
tensor = snack.to_tensor(snd)  # shape (1, n_frames) for mono
```

### Tensor → Sound

```python
import torch
import snack

# (1, n_frames) float32 tensor → Sound
tensor = torch.zeros(1, 16000, dtype=torch.float32)
snd = snack.from_tensor(tensor, sample_rate=16000)

# Works with grad-enabled tensors (detach is called internally)
snd2 = snack.from_tensor(some_tensor.requires_grad_(True), sample_rate=16000)
```

### Use with torchaudio pipelines

```python
import torchaudio
import snack

# Load with torchaudio, process, export to snack for playback
waveform, sr = torchaudio.load("speech.wav")
# ... torchaudio transforms ...
snd = snack.from_tensor(waveform, sample_rate=sr)
snd.play(blocking=True)

# Or: load with snack, convert for a PyTorch model
snd = snack.Sound()
snd.read("speech.wav")
tensor = snack.to_tensor(snd)       # (1, frames), float32
# ... model inference ...
```

---

## Compatibility matrix

| Package    | Minimum version | Required? |
|------------|-----------------|-----------|
| numpy      | 1.21            | Optional  |
| librosa    | 0.9             | Optional  |
| torch      | 1.10            | Optional  |

| Python | Status       |
|--------|--------------|
| 3.8    | Supported    |
| 3.9    | Supported    |
| 3.10   | Supported    |
| 3.11   | Supported    |
| 3.12   | Supported    |

| OS      | Status                                   |
|---------|------------------------------------------|
| Linux   | Supported (ALSA or OSS audio driver)     |
| macOS   | Supported (CoreAudio)                    |
| Windows | Supported (DirectSound via MinGW/MSVC)   |

---

## Running the Python tests

```sh
cd python/
pip install ".[dev]"        # installs pytest + numpy
python -m pytest tests/ -v
```

Integration tests that require the compiled C extension and/or optional
packages (torch, librosa) are automatically skipped when those packages
are absent.

---

## Migration guide: tkSnack → snack

The `tkSnack` module (which required a live Tk window) is deprecated as of
v2.2.10 and will be removed in a future major release.  Here is a mapping
of common patterns:

### Initialisation

```python
# OLD (tkSnack)
from tkinter import *
root = Tk()
import tkSnack
tkSnack.initializeSnack(root)
s = tkSnack.Sound()

# NEW (snack)
from snack import Sound
s = Sound()
```

### Loading and playing

```python
# OLD
s = tkSnack.Sound(load="hello.wav")
s.play()

# NEW
s = Sound()
s.read("hello.wav")
s.play(blocking=True)
```

### Sample data access

```python
# OLD
samples = s.get("samples")

# NEW (NumPy)
import snack
arr = snack.to_numpy(s)   # float32, shape (frames,) or (channels, frames)
```

### Analysis

```python
# OLD
pitch = s.pitch()
power = s.power()

# NEW (identical API via C extension)
from snack import Sound
s = Sound()
s.read("speech.wav")
pitch = s.pitch()
power = s.power()
```

---

## License

GPL-2.0-or-later (inherited from the Snack Toolkit).
