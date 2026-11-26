# Test fixtures: credits and provenance

The media files under `tests/fixtures/` are small samples used only to exercise
the pipeline in automated tests. They do not contain research-participant data.

## Video

- `sample_face.mp4` and the derived `mini_session/videos/mini_session_masked_0.mp4`
  are based on a free stock clip from Pexels (video 855565,
  https://www.pexels.com/video/855565/), used under the
  [Pexels License](https://www.pexels.com/license/) (free to use, including
  commercially; attribution not required). The clip was trimmed and downscaled
  for testing, and the masked version is the output of the anonymization step.

## Sensor CSVs

- The CSV fixtures under `mini_session/` and `raw_session/` are synthetic or
  simulated sensor records generated for testing. Device-position names
  (e.g., Right Pocket, Backpack) are placeholders, not real subjects.
