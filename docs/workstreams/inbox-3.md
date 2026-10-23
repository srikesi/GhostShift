# Inbox: workstream 3

Requests from other workstreams. Add entries at the end, dated, with what you need and why. The owner marks each one done.

## 2026-10-23 — from Jaffer's session (data-center retarget)
- The demo now targets data-center cooling: `VMC-07` → `CRAH-07` (computer room air handler) and `CMP-02` → `CH-02` (air-cooled screw chiller); package `faultzy` → `ghostshift`, env prefix `GHOSTSHIFT_`. `tests/conftest.py` exports `CRAH`, `CH` (was `VMC`, `CMP`).
- Your multimodal stream merged cleanly; I only changed `tests/test_data_multimodal_stream.py` to import `CRAH` instead of `VMC`.
- Suggestion: rename `VMC-07-MULTIMODAL` and its spindle components to data-center equipment (e.g. a CRAH fan or chiller compressor) so the product stays consistent. Your call.
