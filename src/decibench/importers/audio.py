"""Importer for raw audio files — transcribe, diarize, and store as CallTrace."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from decibench.audio.loader import AudioLoadError, load_audio_file
from decibench.models import (
    AgentEvent,
    AudioBuffer,
    CallTrace,
    EventType,
    TranscriptResult,
    TranscriptSegment,
)
from decibench.providers.registry import get_stt

if TYPE_CHECKING:
    from decibench.config import DecibenchConfig

logger = logging.getLogger(__name__)


class AudioImporter:
    """Import a raw audio call recording into the Decibench store."""

    def __init__(self, config: DecibenchConfig) -> None:
        self._config = config
        self._stt = get_stt(config.providers.stt) if config.providers.stt else None

    async def import_file(
        self,
        file_path: Path,
        *,
        source: str = "upload",
        metadata: dict[str, Any] | None = None,
        agent_name: str = "",
        diarize: bool = False,
    ) -> CallTrace:
        """Import a single audio file.

        Args:
            file_path: Path to the audio file.
            source: Source label (e.g., 'upload', 'batch').
            metadata: Optional metadata dict.
            agent_name: Name/identifier of the agent being evaluated.
            diarize: If True, attempt speaker diarization. If False, treat
                     entire audio as a single caller turn (useful when you
                     only have the caller side and will test against a live agent).

        Returns:
            A CallTrace ready for storage and evaluation.
        """
        # 1. Load and normalize audio
        try:
            audio = load_audio_file(file_path)
        except AudioLoadError:
            raise

        # 2. Transcribe
        if self._stt is None:
            raise RuntimeError("No STT provider configured. Set [stt] in decibench.toml.")

        transcript = await self._stt.transcribe(audio)

        # 3. Build segments
        segments: list[TranscriptSegment] = []
        if diarize:
            segments = await self._diarize_and_split(audio, transcript)
        else:
            # Single-speaker fallback: treat everything as caller
            for seg in transcript.segments:
                segments.append(
                    TranscriptSegment(
                        role="caller",
                        text=seg.text,
                        start_ms=seg.start_ms,
                        end_ms=seg.end_ms,
                        confidence=seg.confidence,
                    )
                )

        # 4. Build events from transcript (best-effort for evaluators)
        events: list[AgentEvent] = []
        for seg in segments:
            if seg.role == "agent":
                events.append(
                    AgentEvent(
                        type=EventType.AGENT_TRANSCRIPT,
                        timestamp_ms=seg.start_ms,
                        data={"text": seg.text, "confidence": seg.confidence},
                    )
                )

        # 5. Assemble CallTrace
        trace = CallTrace(
            id=str(uuid.uuid4()),
            source=source,
            target=agent_name,
            started_at=datetime.now(UTC).isoformat(),
            duration_ms=audio.duration_ms,
            transcript=segments,
            events=events,
            metadata={
                "file_name": file_path.name,
                "file_size_bytes": file_path.stat().st_size,
                "sample_rate": audio.sample_rate,
                "channels": audio.channels,
                **(metadata or {}),
            },
            imported_at=datetime.now(UTC).isoformat(),
        )

        return trace

    async def _diarize_and_split(
        self, audio: AudioBuffer, transcript: TranscriptResult
    ) -> list[TranscriptSegment]:
        """Run speaker diarization and map STT segments to caller/agent roles.

        Fallback strategy if pyannote is unavailable:
          - Use a simple energy-based voice-activity heuristic.
          - Or assume alternating turns starting with caller.
        """
        # Placeholder for pyannote.audio integration
        # In production, you would:
        #   from pyannote.audio import Pipeline
        #   pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization")
        #   diarization = pipeline(audio_file)
        # Then map STT word timestamps to diarization speaker labels.

        # Simple fallback: alternate caller/agent every 8 seconds of speech
        # (good enough for MVP; replace with real diarization later)
        segments: list[TranscriptSegment] = []
        current_role: str = "caller"
        last_flip = 0.0

        for seg in transcript.segments:
            # Flip role every ~8 seconds of accumulated speech
            if seg.start_ms - last_flip > 8000:
                current_role = "agent" if current_role == "caller" else "caller"
                last_flip = seg.start_ms

            segments.append(
                TranscriptSegment(
                    role=current_role,  # type: ignore[arg-type]
                    text=seg.text,
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                    confidence=seg.confidence,
                )
            )

        return segments
