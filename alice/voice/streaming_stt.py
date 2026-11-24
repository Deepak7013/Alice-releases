"""Local sherpa-onnx streaming speech recognition helpers for ALICE.

Audio is processed in-process and is never uploaded or saved by this module.
The optional model is kept in the current user's local application-data folder.
"""
from __future__ import annotations

import os
from pathlib import Path


MODEL_NAME = "sherpa-onnx-streaming-zipformer-en-20M-2023-02-17"


def default_model_directory() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".local" / "share"
    return base / "ALICE" / "speech_models" / MODEL_NAME


def model_directory(configured: str = "") -> Path:
    value = str(configured or "").strip()
    return Path(value).expanduser() if value else default_model_directory()


def _model_files(directory: Path) -> tuple[Path, Path, Path, Path]:
    if not directory.is_dir():
        raise FileNotFoundError(
            "The local streaming speech model is not installed. Run "
            "scripts\\setup_streaming_speech.py, then restart listening."
        )

    tokens = directory / "tokens.txt"
    encoder = directory / "encoder-epoch-99-avg-1.int8.onnx"
    decoder = directory / "decoder-epoch-99-avg-1.onnx"
    joiner = directory / "joiner-epoch-99-avg-1.int8.onnx"
    missing = [path.name for path in (tokens, encoder, decoder, joiner)
               if not path.is_file() or path.stat().st_size <= 0]
    if missing:
        raise FileNotFoundError(
            "The local streaming model is incomplete (missing " + ", ".join(missing) + "). "
            "Run scripts\\setup_streaming_speech.py to repair it."
        )
    return tokens, encoder, decoder, joiner


def create_online_recognizer(directory: str | Path | None = None, *, num_threads: int | None = None):
    """Load ALICE's compact English streaming model with low-latency endpointing."""
    try:
        from sherpa_onnx import OnlineRecognizer
    except Exception as exc:
        raise RuntimeError(
            "The sherpa-onnx runtime is not installed. Install "
            "requirements_streaming_stt.txt in ALICE's environment."
        ) from exc

    tokens, encoder, decoder, joiner = _model_files(
        model_directory(str(directory or ""))
    )
    threads = int(num_threads or min(4, max(1, os.cpu_count() or 1)))
    return OnlineRecognizer.from_transducer(
        tokens=str(tokens), encoder=str(encoder), decoder=str(decoder), joiner=str(joiner),
        num_threads=max(1, min(4, threads)), sample_rate=16000, feature_dim=80,
        enable_endpoint_detection=True,
        rule1_min_trailing_silence=0.9,
        rule2_min_trailing_silence=0.35,
        rule3_min_utterance_length=20.0,
        decoding_method="greedy_search", provider="cpu", debug=False,
    )


def pcm16_to_float(pcm: bytes):
    """Convert a microphone PCM16 block to sherpa's normalized float samples."""
    import numpy as np
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0

