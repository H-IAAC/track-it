# Offline Installation — **Target Machine Without Internet Only**

> **Note:** This directory is strictly intended for scenarios where the package must be installed on a machine **without internet access** (e.g., air-gapped network, regulated environment, field equipment). If the host running Face Masking Studio has internet access, **ignore this directory** and follow the main project `README.md`.

The offline workflow consists of:

1. On a **machine with internet access**, download all dependencies (Python wheels + system `.deb` packages) into this repository.
2. Package the entire repository and transfer it (via USB, scp, external drive) to the **offline machine**.
3. On the offline machine, install everything from the pre-downloaded files without requiring any network connectivity.

The scripts operate relative to the repository root, producing `offline/wheels/`, `offline/apt_debs/`, etc.

## Scripts & Files

| File | Purpose |
|---|---|
| `setup.sh` | Runs on the **offline machine** — sets up the venv using `offline/wheels/` (zero network usage). |
| `prepare_offline.sh` | Runs on the **online machine** — downloads Python wheels into `offline/wheels/`, including `onnxruntime-gpu` + CUDA 12 libraries (`nvidia-*-cu12`). Supports cross-targeting by default (e.g., run on Python 3.11 to download 3.12 wheels). |
| `prepare_offline_apt.sh` | Runs on the online machine with the **same Ubuntu version** as the offline host — downloads `.deb` packages for `ffmpeg` and dependencies into `offline/apt_debs/`. |
| `prepare_offline_apt_docker.sh` | Same as above, but runs in a Docker container when the online host has a **different** Ubuntu version than the target. Outputs to `offline/apt_debs_24_04/` or `offline/apt_debs_22_04/`. |
| `check_nvidia_repo.sh` | Diagnostic tool — checks NVIDIA drivers and kernel headers available on Ubuntu 24.04 (runs in Docker). |

## Step-by-Step Guide

### 1. Online Machine — Download Dependencies

```bash
# From the project root:
chmod +x offline/*.sh

# 1a. Python Wheels (GPU/CUDA 12, Python 3.12, x86_64 — default, ~1.5 GB)
./offline/prepare_offline.sh
# Variants:
PY_VERSION=311 ./offline/prepare_offline.sh                  # Python 3.11

# 1b. System .deb packages (ffmpeg)
# If the current machine runs the SAME Ubuntu version as the target:
./offline/prepare_offline_apt.sh
# If different (Docker container matching target version):
UBUNTU=24.04 ./offline/prepare_offline_apt_docker.sh
UBUNTU=22.04 ./offline/prepare_offline_apt_docker.sh
```

Package the whole repository:

```bash
cd ..
tar --exclude='face-masking-studio/backend/.venv' -czf face-masking-studio-offline.tar.gz face-masking-studio/
```

Transfer the `.tar.gz` archive to the offline target machine.

### 2. Offline Machine — Installation

```bash
tar -xzf face-masking-studio-offline.tar.gz
cd face-masking-studio

# 2a. System packages (ffmpeg)
sudo dpkg -i offline/apt_debs/*.deb              # Case A (matching Ubuntu version)
# or
sudo dpkg -i offline/apt_debs_24_04/*.deb        # Case B, Ubuntu 24.04
sudo dpkg -i offline/apt_debs_22_04/*.deb        # Case B, Ubuntu 22.04

# 2b. Virtualenv + Python packages (offline)
./offline/setup.sh
# To explicitly select Python interpreter:
PYTHON=python3.12 ./offline/setup.sh
```

### 3. Running

Same as online mode:

```bash
source backend/.venv/bin/activate
cd backend
uvicorn main:app --host 127.0.0.1 --port 8000
```

## Technical Details

- **No `python3.X-venv` apt package needed:** `offline/setup.sh` uses `python -m venv --without-pip` and installs pip by executing the pip wheel directly as a zipapp (`python offline/wheels/pip-X.Y.whl/pip install pip`), avoiding `ensurepip`.
- **Python version matching:** `offline/setup.sh` inspects the `cpXXX` tag of wheels in `offline/wheels/` and aborts with a clear message if the Python interpreter version does not match.
- **ONNX models:** (`backend/models/*.onnx`) are already tracked in the repository.
- **GPU without system-wide CUDA:** `requirements.txt` bundles `onnxruntime-gpu` + `nvidia-*-cu12` wheels (CUDA 12 runtime + cuDNN 9). `config.py` calls `onnxruntime.preload_dlls()` upon import, allowing full GPU acceleration **without** installing CUDA Toolkit/cuDNN via apt. **The only system requirement is the kernel NVIDIA driver** (not distributable via pip). Without the driver, execution falls back to CPU automatically.
- **`.gitignore`** ignores `offline/wheels/`, `offline/apt_debs/`, and `offline/apt_debs_*/` so binary artifacts are never committed by mistake.

## Troubleshooting

| Symptom | Solution |
|---|---|
| `offline/setup.sh` aborts with "Python version mismatch" | Install the Python version matching the downloaded wheels, or re-download with `PY_VERSION=3XX ./offline/prepare_offline.sh` on the online machine. |
| Message requesting `python3.10-venv` | System `python3` points to a different version. Run `PYTHON=python3.12 ./offline/setup.sh`. |
| `ensurepip is not available` | Some Linux distributions strip `ensurepip`. Install the matching `python3.X-venv` `.deb` package (`apt-get download python3.12-venv` on the online machine). |
| `dpkg` complains about dependency order | Run `sudo apt-get install -f --no-download`. |
