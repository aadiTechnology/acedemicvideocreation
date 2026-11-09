# Sprint 7 POC report: Class 7 Science, Nutrition in Plants / Photosynthesis

Three videos, one per language, each made through the real chain: Academic API (import, approve, generate) -> Video Engine API -> worker -> MP4 -> Academic storage -> download. Content is in `docs/poc/<language>/` (10 slides each). The run is reproducible with `docs/poc/run_poc.py`.

**Overall: the pipeline works for all three languages. Hindi and Marathi narration is NOT validated (BLOCKED), and the English voice is only a test voice.** Do not present these as final videos.

## Results

| Language | Duration | Resolution | Codec | Decode errors | Size |
|---|---|---|---|---|---|
| English | 4:02 | 1920x1080 @ 24 fps | h264 + audio | none | 6.71 MB |
| Hindi | 4:07 | 1920x1080 @ 24 fps | h264 + audio | none | 2.14 MB |
| Marathi | 4:04 | 1920x1080 @ 24 fps | h264 + audio | none | 2.05 MB |

## Validation against the POC criteria

| Criterion | English | Hindi | Marathi |
|---|---|---|---|
| Script written, in the import format, imported and approved through the app | PASS | PASS | PASS |
| **Script correctness (subject expert review)** | BLOCKED: drafted for review; no expert has reviewed it | BLOCKED: needs a native-speaker science reviewer | BLOCKED: same |
| **Pronunciation / voice** | PARTIAL: free Windows test voice (US English accent), not the production voice | **BLOCKED**: no Hindi voice available here (Colab not run); audio is silent placeholder | **BLOCKED**: same |
| Slides match the audio (checked with a frame from the middle of each slide's audio window; the on-screen counter matches the slide) | PASS | PASS (placeholder timing) | PASS (placeholder timing) |
| **Caption sync with real speech** | PASS in timing logic; not independently checked against a human ear | **BLOCKED** (no speech) | **BLOCKED** (no speech) |
| Devanagari text shaping on slides and captions | n/a | PASS (visual check of contact sheet) | PASS (visual check of contact sheet) |
| Visuals / animation | LIMITED: clean text slides (headline and bullets). No diagrams, pictures or animation | same | same |
| MP4 valid: H.264 + AAC, 1920x1080, 24 fps, decodes with no errors | PASS | PASS | PASS |
| Duration about 5 minutes | PASS: 4:02 (script is 242.2 s of narration) | PASS: 4:07 | PASS: 4:04, but placeholder timing; real Marathi speech may be shorter or longer |
| Reproducibility (same package and audio rendered twice) | PASS: video frames identical = True, audio identical = True, file bytes identical = True | not run | not run |
| End to end without copying files between the two apps | PASS | PASS | PASS |

## What the POC found and fixed

1. **Captions showed one word at a time.** The engine times captions from `subtitle_text` and splits any cue longer than 7 seconds, so a short summary there is shown word by word. Fix: `subtitle_text` carries the narration; short on-slide wording moved to `lesson_plan.json` `slides` (headline and bullets), which the slide renderer now draws. The Academic prompt specification, validation (new `plan_slides` checks and a short-subtitle warning) and the API contract were updated.
2. **Slides were a single line of text.** They now show a headline and up to five bullets.
3. Baseline before the fixes: English 4:02, Hindi 4:07, Marathi 4:04 (kept in `baseline-before-fixes/`).

## What is needed to finish validation

1. Run `notebooks/colab_tts.ipynb` on Colab (GPU) for each language version, upload the narration ZIP in the app, and listen. Check the model licence (AI4Bharat Indic Parler-TTS) and pronunciation of scientific terms in Hindi and Marathi. If quality is not acceptable, evaluate another open model or use Azure as a fallback.
2. A subject expert (and a native speaker for Hindi and Marathi) reviews the scripts in the app and approves.
3. Decide whether text-only slides are acceptable, or add supplied images or diagrams (the package already accepts PNG/JPEG in `assets/`).

## Files

`results/photosynthesis-<lang>.mp4` (not committed, large), `results/contact-<lang>.png` (one frame per slide), `results/poc_results.json`, `baseline-before-fixes/`.
