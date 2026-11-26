# hiaac-theme

Single source of the H.IAAC visual identity used by every tool in the toolkit.

| Path | Contents |
|---|---|
| `web/hiaac.css` | Color tokens (light and dark), typography, brand header, buttons, cards, inputs, dropdowns. |
| `web/hiaac-theme.js` | Light/dark toggle stored in `localStorage` (`data-theme` on `<html>`). |
| `web/hiaac-logo.svg` | H.IAAC logo used in the header of every tool. |
| `web/fonts/` | JetBrains Mono (woff2), loaded locally with no CDN. |
| `android/colors.xml`, `android/colors-night.xml` | Same palette for the Android modules. |

## Main tokens

| Token | Light | Use |
|---|---|---|
| `--paper` | `#f4f0e9` | Background |
| `--ink` | `#1d1a16` | Main text |
| `--accent` | `#ff9d1c` | H.IAAC orange: primary actions, active state |
| indigo / sage / blue / red | `#5750c4` / `#5d7f4c` / `#3a6db0` / `#b8392b` | Secondary data series, success, info, destructive |

Controls use a 3px radius and cards a 4px radius. The logo in the header is 42px high.

## Sync

```bash
./shared/hiaac-theme/sync.sh
```

The script copies the web theme to:

- `face_masking_studio/frontend/hiaac/`
- `server-processing/preprocessor/public/hiaac/`
- `annotation_interface/assets/hiaac/`
- `viewer_interface/assets/hiaac/`

Commit the copies too, so that each tool runs on its own. The Android colors in `android/` are not copied by the script; keep them in sync by hand with `android_app/*/app/src/main/res/values{,-night}/colors.xml`.

## Credits

The bundled [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) font is licensed under the SIL Open Font License 1.1 (`web/fonts/OFL.txt`, copied to every tool by `sync.sh`).
