import numpy as np

from src.live.timeline import AlignedMixer, SourceTimeline
from src.live.types import CaptureEventKind, CaptureSource, PcmChunk


def chunk(
    offset: int,
    frames: list[float],
    source: CaptureSource = CaptureSource.MIC,
) -> PcmChunk:
    return PcmChunk(
        source,
        48_000,
        1,
        offset,
        np.asarray(frames, dtype=np.float32).reshape(-1, 1).copy(),
        1,
    )


def test_timeline_inserts_silence_for_offset_gap():
    timeline = SourceTimeline(CaptureSource.MIC, sample_rate=48_000, channels=1)

    timeline.ingest(chunk(0, [0.5, 0.5]))
    emitted = timeline.ingest(chunk(5, [0.25]))

    assert emitted[0].frames.tolist() == [[0.0], [0.0], [0.0]]
    assert emitted[0].sample_offset == 2
    assert emitted[-1].sample_offset == 5


def test_timeline_discards_previously_emitted_overlap_and_reports_it():
    events = []
    timeline = SourceTimeline(
        CaptureSource.MIC,
        sample_rate=48_000,
        channels=1,
        on_event=events.append,
    )

    timeline.ingest(chunk(0, [0.1, 0.2, 0.3]))
    emitted = timeline.ingest(chunk(2, [0.3, 0.4, 0.5]))

    assert emitted[0].sample_offset == 3
    assert np.allclose(emitted[0].frames, [[0.4], [0.5]])
    assert events[-1].kind is CaptureEventKind.DISCONTINUITY
    assert "overlap=1" in events[-1].detail


def test_timeline_keeps_emitted_offsets_monotonic_for_gaps_and_overlaps():
    timeline = SourceTimeline(CaptureSource.MIC, sample_rate=48_000, channels=1)
    chunks = [chunk(0, [0.1, 0.2]), chunk(5, [0.3]), chunk(4, [0.4, 0.5, 0.6])]

    emitted = [part for audio in chunks for part in timeline.ingest(audio)]

    assert [part.sample_offset for part in emitted] == [0, 2, 5, 6]
    assert emitted[1].frames.tolist() == [[0.0], [0.0], [0.0]]


def test_timeline_preserves_monotonic_offsets_for_seeded_gaps_and_overlaps():
    random = np.random.default_rng(0)
    timeline = SourceTimeline(CaptureSource.MIC, sample_rate=48_000, channels=1)
    expected_next = 0
    emitted = []

    for _ in range(20):
        offset = max(0, expected_next + int(random.integers(-2, 4)))
        frame_count = int(random.integers(1, 5))
        parts = timeline.ingest(chunk(offset, random.uniform(-1, 1, frame_count).tolist()))
        emitted.extend(parts)
        if parts:
            expected_next = parts[-1].sample_offset + len(parts[-1].frames)

    assert [part.sample_offset for part in emitted] == sorted(part.sample_offset for part in emitted)
    assert all(part.frames.dtype == np.float32 for part in emitted)


def test_mixer_applies_gains_and_clips_to_audio_range():
    mixer = AlignedMixer(mic_gain=1.0, system_gain=1.0)

    mixed = mixer.mix(
        {
            CaptureSource.MIC: chunk(0, [0.8, -0.8]),
            CaptureSource.SYSTEM: chunk(0, [0.7, -0.7], CaptureSource.SYSTEM),
        }
    )

    assert mixed.frames.tolist() == [[1.0], [-1.0]]
