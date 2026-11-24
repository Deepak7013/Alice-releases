# ALICE local voice package

This package contains only the two selected Kokoro voices:

- Heart (`af_heart`), US English female
- Fable (`bm_fable`), British English

Both use the same upstream Kokoro v1.0 full precision ONNX model. The ONNX
speaker metadata was narrowed to these two profiles, and `voices.bin` contains
only their 510 × 1 × 256 float32 style tensors, ordered Heart then Fable. The
speech network weights were not changed. The paired profiles synthesize through
the bundled sherpa-onnx runtime at 24 kHz.

The original 54-profile voice table was 28,200,960 bytes. The two-profile table
is 1,044,480 bytes, saving 27,156,480 bytes. The shared ONNX model remains
325,558,709 bytes and is required by both voices. English lexicons and eSpeak-NG
data are included for pronunciation. The upstream Kokoro license is in
`LICENSE`.

ALICE intentionally does not download a full voice archive at runtime. If the
bundled model is missing, repair or reinstall ALICE to restore this compact
two-voice package.
