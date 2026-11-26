# Track-It Server (Server Processing)

- **preprocessor/**: Node.js (Express + EJS) web tool. It receives the files sent by the app (`/api/file`, `/api/video`), handles authentication, and shows the experiments, files, and plots in the H.IAAC theme.
- **postprocessor/**: Python tool. It watches the input folder, cleans the CSVs, checks the timelapse, syncs the sensors with the video, splits the data into one file per sensor, and writes the session to `data/`.
- **run.sh**: starts both, used inside Docker.

## Data flow

```text
android app ─► preprocessor (8080) ─► preprocessor/_preprocessor/<session>/
                                              │ (watchdog)
                                              ▼
                                  postprocessor (7998) ─► ../data/<session>/
                                              │
                                              └─► Track-It Masking Studio (8000): auto-anonymize
```

- **Input:** `preprocessor/_preprocessor/` (`PRE_DIR` in both `run.sh` files). A session folder holds the raw CSVs, `session_manifest.json`, and optionally `<video>.mp4` and `<video>.video`. You can also copy a session folder there by hand.
- **Output:** `../data/<session>/` (`POST_DIR`), with `raw_sensors/`, `sensors/`, `videos/`, and the updated `session_manifest.json`. The manifest gets:
  - `raw_sensors` as `raw_sensors/<file>`;
  - `clean_sensors` (mapped to `sensors/<sensor>_<device>.csv`);
  - `raw_video`;
  - `pipeline_status.server_processed = true`.
- **Automatic masking:** when the session has a video, the postprocessor calls `POST http://localhost:8000/api/video/dataset:<session>/auto-anonymize`.
  - **Prerequisite:** The Face Masking Studio must be running on port `8000` prior to processing; if it is not, the session is processed without anonymized video output.
  - **Progress Visibility:** The auto-anonymization process runs asynchronously on Face Masking Studio. Progress (tracking and rendering percentage) is logged to the Face Masking Studio console / terminal (`run_all.sh logs face-mask`).
- The postprocessor only reacts to **new** folders (`on_created`). To process a folder again, move it out of `_preprocessor/` and copy it back in.

## Network & Firewall Setup

- **Network Bind:** The preprocessor listens on `0.0.0.0:8080`, allowing incoming file uploads and clock synchronization HTTP requests from any device on the local network (LAN).
- **Firewall Notice:** If the server host has an active firewall (e.g. Linux UFW/iptables, Windows Defender Firewall), make sure port **`8080`** is allowed for inbound connections from the local subnet. If blocked, mobile phones will be unable to establish connection or sync timestamps.

## Run without Docker

You need:

- Node.js 18 or newer and npm;
- Python 3.12 or newer;
- `ffmpeg` and `libmediainfo`.

```bash
# Python dependencies (or use the root .venv with requirements_cpu.txt)
pip install -r postprocessor/requirements.txt

# Preprocessor
cd preprocessor
npm install
./run.sh start 8080        # http://127.0.0.1:8080

# Postprocessor (uses ../../.venv when it exists)
cd ../postprocessor
./run.sh start 7998
```

- Use `./run.sh stop` and `./run.sh status` in each folder to stop the service or check it.
- Logs go to `preprocessor/log_pre.out` and `postprocessor/logs/`.
- The JWT signing key is not stored in the repo: set `JWT_KEY` in the environment to keep logins valid across restarts; otherwise a random key is generated at startup.
- The web UI login uses the bcrypt hash in `preprocessor/config/config.json`. The value shipped in the repo is the hash of the default password `changeme`, meant only to get you running; **change it before any real deployment**. To make a new hash, run `node config/gen_password.js <password>` and put the result in the `password` field.

## Run with Docker

The image uses the code of your current branch, so check that you are on the right branch. Review `preprocessor/config/config.json` (password and token URLs) before building.

```bash
docker compose -f docker-compose_cpu.yml build   # only when building a new image
docker compose -f docker-compose_cpu.yml up
```

The compose file mounts `./files/pre` and `./files/post` as the input and output folders.

## Version 4.0 tests and results

| Test | Video | Processing time | Frames with mask |
|---|---|---|---|
| Static | 13.10 min | 6.53 min | 97.79% |
| Bench | 13.30 min | 6.59 min | 96.68% |
| Indoor/Final | 2.45 min | 1.36 min | 99.42% |

Full results: [Tests results](https://drive.google.com/file/d/1G-EFDLe-UU6y-JhldMcDE6GRYTQBmiMx/view?usp=sharing)

## Overview:
![image](https://github.com/H-IAAC/viewer_tool/assets/117912051/1f22038c-1ac9-4baf-b62f-24199b02e7e5)

## Workflow:
![image](https://github.com/H-IAAC/viewer_tool/assets/117912051/8c9757e7-24d1-45ee-981a-bb88e9c57bed)

## Testing:
This solution follows the REST (Representational State Transfer) software architectural style, as illustrated in the diagrams above, there are some APIs that can be used by external tools to interact with this solution.
> These APIs are intented to be used by the Android mobile app and the Jupyter notebook, but it is also accessable to any other tool. Nowadays there are lots of different REST tools available, as Postman, Insomnia, EchoAPI, SoapUI, cURL just to cite a few.
So in order to simulate or test this solution, you can choose any REST tools of you preference.
### Send files to the server
### Sending a file (.zip or .csv)
To simulate a HTTP request, we need 2 configurations:
```
URL: http://<address>:<port>/api/file
Parameters: File (.zip or .cvs), experiment, subject, activity
```
#### Example:
Using Insomnia tool to POST a file.
![image](https://github.com/user-attachments/assets/57d968b3-7208-4684-a592-a86552ed9f6c)


### Sending a video (.mp4)
To simulate a HTTP request, we need 2 configurations:
```
URL: http://<address>:<port>/api/video
Parameters: File (.mp4), videoDuration, startTimestamp, endTimestamp and directory
```
**Note:** where *directory* format is '_experiment [activity] [subject]_'
#### Example:
Using Insomnia tool to POST the video file.
![image](https://github.com/user-attachments/assets/662718da-0e84-4161-bf61-f43850b0223f)





## Credits and license

MIT (see `../LICENSE`). Based on [H-IAAC/data_collection_server](https://github.com/H-IAAC/data_collection_server) (commit `89ce88f`, branch `v4.1`), developed by H.IAAC and Instituto Eldorado ([Saulo A. Moraes](https://github.com/saulo-moraes), [Amparo Díaz Muñoz](https://github.com/amparomunoz) and contributors) and released here under MIT with their authorization; see `../THIRD_PARTY_NOTICES.md` for what changed. The Watch page bundles [d3.js](https://github.com/d3/d3) v4.13.0 by Mike Bostock (ISC) in `preprocessor/public/graph/d3.v4.js`. The upstream Ultralytics-based video converters (AGPL-3.0 dependency) were removed; masking now goes through the Face Masking Studio API.
