#!/usr/bin/env bash
# Run this on the OFFLINE machine. Builds a venv from the local wheels/
# folder produced by prepare_offline.sh.
#
# Usage:
#   ./setup.sh                       # auto-detects a python that matches the wheels
#   PYTHON=python3.12 ./setup.sh     # force a specific interpreter
#
# Notes:
#   - Uses `python -m venv --without-pip` so it does NOT require the
#     distro's python3.X-venv apt package.
#   - Bootstraps pip by running the bundled pip wheel directly as a zipapp
#     (`python wheels/pip-X.Y.whl/pip install pip`). This sidesteps
#     `ensurepip`, which is also part of the python3.X-venv apt package.
#   - Verifies that the chosen Python's cpXXX tag matches the wheels
#     in wheels/ before doing anything destructive.

set -euo pipefail
# this script lives in offline/ — operates on project root
cd "$(dirname "$0")/.."

VENV_DIR="backend/.venv"

if [ ! -d offline/wheels ] || [ -z "$(ls -A offline/wheels 2>/dev/null)" ]; then
    echo "ERROR: wheels/ folder missing or empty." >&2
    echo "  Run prepare_offline.sh on an internet-connected machine first," >&2
    echo "  then transfer the entire release/ folder here." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 1. Detect the cpython tag baked into the wheel filenames.
# ---------------------------------------------------------------------------
# Look only at wheels whose Python tag matches the ABI tag (cp312-cp312,
# cp311-cp311, etc.) — those are version-specific. Skip "cp37-abi3" /
# "cp36-abi3" style wheels (stable ABI, compatible with Python 3.X+ and
# therefore not a reliable signal of what the venv needs).
# Use `sort -V | tail -n1` to pick the highest version numerically rather
# than alphabetically (otherwise cp310 sorts before cp312).
WHEEL_CP_TAG="$(
    ls offline/wheels/ \
        | grep -oE 'cp3[0-9]+-cp3[0-9]+' \
        | cut -d- -f1 \
        | sort -uV \
        | tail -n1
)"
if [ -z "$WHEEL_CP_TAG" ]; then
    echo "WARNING: could not detect a version-specific cpXXX tag from wheels/" >&2
    echo "(wheels appear to be pure-Python or abi3-only, so any Python works)" >&2
    WHEEL_PY=""
else
    WHEEL_PY="3.${WHEEL_CP_TAG#cp3}"
    echo "Wheels target Python $WHEEL_PY ($WHEEL_CP_TAG)"
fi

# ---------------------------------------------------------------------------
# 2. Find the pip wheel that we'll use to bootstrap pip into the venv.
# ---------------------------------------------------------------------------
PIP_WHEEL="$(ls offline/wheels/pip-*.whl 2>/dev/null | head -n1 || true)"
if [ -z "$PIP_WHEEL" ]; then
    echo "ERROR: no pip-*.whl found in offline/wheels/." >&2
    echo "  Re-run prepare_offline.sh on the internet machine — it now bundles pip" >&2
    echo "  so the offline setup can bootstrap without ensurepip." >&2
    exit 1
fi
echo "Will bootstrap pip from: $PIP_WHEEL"

# ---------------------------------------------------------------------------
# 3. Pick the python interpreter.
# ---------------------------------------------------------------------------
if [ -n "${PYTHON:-}" ]; then
    PY="$PYTHON"
elif [ -n "$WHEEL_PY" ] && command -v "python$WHEEL_PY" >/dev/null 2>&1; then
    PY="python$WHEEL_PY"
else
    PY="python3"
fi

if ! command -v "$PY" >/dev/null 2>&1; then
    echo "ERROR: interpreter '$PY' not found in PATH." >&2
    if [ -n "$WHEEL_PY" ]; then
        echo "  The wheels in offline/wheels/ were built for Python $WHEEL_PY." >&2
        echo "  Either install python$WHEEL_PY, or rebuild the wheel cache:" >&2
        echo "    on the internet machine:  PY_VERSION=${WHEEL_PY/./} ./prepare_offline.sh" >&2
    fi
    exit 1
fi

PY_FULL="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "Using interpreter: $PY (Python $PY_FULL)"

if [ -n "$WHEEL_PY" ] && [ "$PY_FULL" != "$WHEEL_PY" ]; then
    echo "ERROR: Python version mismatch." >&2
    echo "  Interpreter '$PY' is Python $PY_FULL." >&2
    echo "  Wheels in offline/wheels/ target Python $WHEEL_PY ($WHEEL_CP_TAG)." >&2
    echo >&2
    echo "  Fix one of these:" >&2
    echo "    1. Install python$WHEEL_PY on this machine and re-run setup.sh" >&2
    echo "       (it will auto-detect). Or run:  PYTHON=python$WHEEL_PY ./setup.sh" >&2
    echo "    2. Rebuild wheels on the internet machine for $PY_FULL:" >&2
    echo "       PY_VERSION=${PY_FULL/./} ./prepare_offline.sh" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 4. Build the venv WITHOUT pip — we'll inject it ourselves from the wheel.
# ---------------------------------------------------------------------------
if [ -d "$VENV_DIR" ]; then
    echo "Removing existing $VENV_DIR/"
    rm -rf "$VENV_DIR"
fi

echo "Creating venv (without pip) in $VENV_DIR"
"$PY" -m venv --without-pip "$VENV_DIR"

# Use the venv's python directly via absolute path. We deliberately do NOT
# `source .venv/bin/activate` — `pip` won't be on PATH yet, and any external
# `pip` (system or ~/.local) would silently take over.
VENV_PY="$VENV_DIR/bin/python"

if [ ! -x "$VENV_PY" ]; then
    echo "ERROR: venv python not found at $VENV_PY" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 5. Bootstrap pip by running the pip wheel as a zipapp.
# pip wheels are runnable: `python /path/to/pip-X.Y.whl/pip install ...`
# This is what get-pip.py uses internally, and works without ensurepip.
# ---------------------------------------------------------------------------
echo "Bootstrapping pip into the venv (from wheel, no network, no ensurepip)"
"$VENV_PY" "$PIP_WHEEL/pip" install \
    --no-index --find-links=offline/wheels \
    pip setuptools wheel

# Sanity: confirm pip is now in the venv, not somewhere else.
PIP_LOC="$("$VENV_PY" -c 'import pip, os; print(os.path.dirname(pip.__file__))')"
case "$PIP_LOC" in
    "$PWD/$VENV_DIR"/*) : ;;
    *)
        echo "ERROR: pip ended up outside the venv ($PIP_LOC). Aborting." >&2
        exit 1 ;;
esac
echo "pip is at: $PIP_LOC"

# ---------------------------------------------------------------------------
# 6. Install project dependencies offline.
# ---------------------------------------------------------------------------
REQ_FILE="offline/wheels/active-requirements.txt"
[ -f "$REQ_FILE" ] || REQ_FILE="backend/requirements.txt"
echo "Installing project dependencies from $REQ_FILE (offline)"
"$VENV_PY" -m pip install --no-index --find-links=offline/wheels -r "$REQ_FILE"

# ---------------------------------------------------------------------------
# 7. Smoke test the heavy imports.
# ---------------------------------------------------------------------------
echo
echo "Verifying imports..."
"$VENV_PY" - <<'PY'
import importlib, sys
mods = ['fastapi', 'uvicorn', 'pydantic', 'numpy',
        'cv2', 'onnxruntime', 'ffmpeg']
fail = []
for m in mods:
    try:
        importlib.import_module(m)
        print(f"  ok   {m}")
    except Exception as e:
        print(f"  FAIL {m}: {e}")
        fail.append(m)

# Report the onnxruntime execution providers so it's obvious whether the
# GPU stack actually came up. Missing CUDA usually means the host has no
# NVIDIA driver (pip wheels provide CUDA/cuDNN, but NOT the kernel driver).
try:
    import onnxruntime as ort
    if hasattr(ort, "preload_dlls"):
        ort.preload_dlls()
    providers = ort.get_available_providers()
    print(f"  ort providers: {providers}")
    if "CUDAExecutionProvider" in providers:
        print("  -> GPU acceleration AVAILABLE (CUDAExecutionProvider)")
    else:
        print("  -> running on CPU (no CUDAExecutionProvider).")
        print("     If you expected GPU, install/repair the NVIDIA driver on this host.")
except Exception as e:
    print(f"  WARN could not query onnxruntime providers: {e}")

sys.exit(1 if fail else 0)
PY

cat <<MSG

Setup complete.

Activate the venv with:  source backend/.venv/bin/activate

Next steps:
  1. Start the server:        cd backend && uvicorn main:app --host 127.0.0.1 --port 8000
  2. Open in browser:         http://localhost:8000
MSG
