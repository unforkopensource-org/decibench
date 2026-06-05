"""Audio file loader — normalize any input format to Decibench canonical format."""
from __future__ import annotations
import io
import logging
from pathlib import Path
import numpy as np
import soundfile as sf
from typing import TYPE_CHECKING
from decibench.models import AudioBuffer, AudioEncoding
if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

# Supported extensions in order of preference
SUPPORTED_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".wma"}


class AudioLoadError(Exception):
    """Raised when an audio file cannot be loaded or normalized."""


def load_audio_file(path: Path | str) -> AudioBuffer:
    """Load any supported audio file and return canonical AudioBuffer.

    Pipeline:
    1. Read with soundfile (libsndfile + ffmpeg if available)
    2. Convert to float32 array
    3. Downmix to mono
    4. Resample to 16 kHz
    5. Convert to 16-bit PCM
    """
    path = Path(path)
    if not path.exists():
        raise AudioLoadError(f"File not found: {path}")

    if path.suffix.lower() not in SUPPORTED_EXTS:
        raise AudioLoadError(
            f"Unsupported format '{path.suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTS))}"
        )

    try:
        data, sr = sf.read(str(path), dtype="float32")
    except Exception as e:
        raise AudioLoadError(f"Failed to read audio: {e}") from e

    # Ensure mono format
    if data.ndim > 1:
        data = data.mean(axis=1).astype(np.float32)
    else:
        data = data.astype(np.float32)

    # Resample to 16 kHz if needed
    if sr != 16000:
        # Use librosa for resampling numpy array
        import librosa
        data = librosa.resample(data, orig_sr=sr, target_sr=16000)

    # Convert to 16-bit PCM
    pcm = (data * 32767).clip(-32768, 32767).astype(np.int16)

    return AudioBuffer(
        data=pcm.tobytes(),
        sample_rate=16000,
        channels=1,
        bit_depth=16,
        encoding=AudioEncoding.PCM_S16LE,
    )


def load_audio_bytes(data: bytes, format_hint: str = "wav") -> AudioBuffer:
    """Load audio from in-memory bytes (used by API uploads)."""
    try:
        buf = io.BytesIO(data)
        arr, sr = sf.read(buf, dtype="float32")
    except Exception as e:
        raise AudioLoadError(f"Failed to decode audio bytes: {e}") from e

    # Ensure mono format
    if arr.ndim > 1:
        arr = arr.mean(axis=1).astype(np.float32)
    else:
        arr = arr.astype(np.float32)

    # Resample to 16 kHz if needed
    if sr != 16000:
        import librosa
        arr = librosa.resample(arr, orig_sr=sr, target_sr=16000)

    # Convert to 16-bit PCM
    pcm = (arr * 32767).clip(-32768, 32767).astype(np.int16)

    return AudioBuffer(
        data=pcm.tobytes(),
        sample_rate=16000,
        channels=1,
        bit_depth=16,
        encoding=AudioEncoding.PCM_S16LE,
    )
