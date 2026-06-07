import struct
import wave
from pathlib import Path

import pytest

from decibench.audio.loader import AudioLoadError, load_audio_file
from decibench.config import DecibenchConfig
from decibench.importers.audio import AudioImporter


@pytest.fixture
def dummy_audio_file(tmp_path: Path) -> Path:
    wav_path = tmp_path / "sample_call.wav"
    # Create a simple 1-second mono WAV file at 16kHz PCM S16LE
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(16000)
        # Write 1 second of silent samples (16000 samples)
        w.writeframes(struct.pack("<16000h", *[0] * 16000))
    return wav_path


@pytest.fixture
def dummy_image_file(tmp_path: Path) -> Path:
    png_path = tmp_path / "image.png"
    png_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...")
    return png_path


def test_load_wav(dummy_audio_file):
    buf = load_audio_file(dummy_audio_file)
    assert buf.sample_rate == 16000
    assert buf.channels == 1


def test_load_unsupported(dummy_image_file):
    with pytest.raises(AudioLoadError):
        load_audio_file(dummy_image_file)


@pytest.mark.asyncio
async def test_import_audio(dummy_audio_file, default_config, monkeypatch):
    from decibench.models import TranscriptResult, TranscriptSegment

    class FakeSTT:
        async def transcribe(self, audio):
            return TranscriptResult(
                text="hello world",
                segments=[
                    TranscriptSegment(
                        role="caller", text="hello world", start_ms=0, end_ms=1000, confidence=0.99
                    )
                ],
                language="en",
                duration_ms=1000,
            )

    # Patch get_stt to return our FakeSTT
    monkeypatch.setattr("decibench.importers.audio.get_stt", lambda provider: FakeSTT())

    importer = AudioImporter(default_config)
    trace = await importer.import_file(dummy_audio_file)
    assert trace.duration_ms > 0
    assert len(trace.transcript) > 0
    assert trace.transcript[0].text == "hello world"
