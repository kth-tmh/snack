"""
snack - Python bindings for the Snack Sound Toolkit.

This package provides a direct Python API over the Snack C library without
any Tcl/Tk dependency visible to callers.  The C extension (_snack) embeds
a Tcl interpreter internally for resource management, but you never need
to install or interact with Tcl or Tk yourself.

Quick start::

    from snack import Sound

    s = Sound()
    s.read("speech.wav")
    print(s.length, s.sample_rate, s.channels)
    s.play()

    pitch = s.pitch()
    spectrum = s.power_spectrum(fft_length=1024)
"""

from ._snack import (
    Sound,
    get_output_devices,
    get_input_devices,
    audio_rate,
    LIN16,
    ALAW,
    MULAW,
    LIN8OFFSET,
    LIN8,
    LIN24,
    LIN32,
    SNACK_FLOAT,
    SNACK_DOUBLE,
)

__all__ = [
    "Sound",
    "get_output_devices",
    "get_input_devices",
    "audio_rate",
    "LIN16",
    "ALAW",
    "MULAW",
    "LIN8OFFSET",
    "LIN8",
    "LIN24",
    "LIN32",
    "SNACK_FLOAT",
    "SNACK_DOUBLE",
]

__version__ = "2.2.10"
