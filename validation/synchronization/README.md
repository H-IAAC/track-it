# validation / synchronization

Reproduces the synchronization results reported in the paper: the five-smartphone experiment, the cross-correlation estimate of the lag between devices, and the analysis of drift and waveform agreement. The committed run is the 10 Hz experiment; the 100 Hz run is distributed with the dataset.

## Experimental Setup & Network Architecture

In the validation experiment, the five smartphones (Annotator with video capture, Right Pocket, Left Pocket, Right Hand, Crossbody Bag) and the host server were connected to an **isolated local area network via a dedicated internal Wi-Fi router (no internet WAN)**. This physical setup ensured:
- Complete isolation from external network traffic, campus firewalls, and WAN latency fluctuations.
- Stable, low-latency round-trip times for Cristian's clock synchronization algorithm (`VideoTimelapse` time base alignment).
- Consistent multi-device data ingestion into `server-processing`.

## Contents (`sync/`)

| File | What |
|---|---|
| `sync_analysis.ipynb` | Full analysis: events, activity windows, lag, sync jitter, sampling jitter, drift, and figures |
| `sync_experiments/pre`, `sync_experiments/post` | Collection before and after the server postprocessor (one CSV per sensor and device) |
| `sync_experiments/terminal_stopwatch` | Reference stopwatch recording |
| `sync_collection_notes.txt` | Start and end times of each movement (table, vertical, horizontal) |
| `detected_events.csv`, `annotated_activity_windows.csv` | Detected events and annotated windows |
| `lag_matrix_ms.csv`, `lag_jitter_matrix_ms.csv`, `sampling_jitter.csv`, `device_synchronization.csv`, `synchronization_per_window.csv` | Aggregated results |
| `fig_overview.png`, `fig_overlay_table.png`, `fig_lag_stability.png`, `sync_table.png` | Figures and summary table |

Devices follow the paper naming: Annotator, Right Pocket, Left Pocket, Right Hand, Crossbody Bag.

## Run

```bash
pip install -r ../../requirements_cpu.txt     # Python 3.12 or newer
jupyter nbconvert --to notebook --execute --inplace sync/sync_analysis.ipynb
```
