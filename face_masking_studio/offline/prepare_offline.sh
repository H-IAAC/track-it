#!/usr/bin/env bash
# Run this on a machine WITH internet. It downloads every wheel + sets up
# the local cache so the offline target machine can install without network.
#
# By default we CROSS-TARGET: the wheels are downloaded for a specific Python
# version + platform (linux_x86_64), independent of what's installed on the
# current machine. That lets you prepare on Python 3.11 and ship to a machine
# running Python 3.12.
#
# Usage:   ./prepare_offline.sh [requirements_file] [platform]
#
# Environment:
#   PY_VERSION=312   target Python version on the offline machine (default 312)
#                    use 311 if the offline machine runs Python 3.11.
#
# Platform values:
#   linux_x86_64      — manylinux x86_64 family (default; what offline machines use)
#   linux_aarch64     — manylinux aarch64 family (cross-target to ARM64 Linux)
#   auto              — current machine's compatibility tags
#                       (only useful if you prepare + run on the SAME machine
#                        with the SAME python version)
#
# backend/requirements.txt now pins onnxruntime-gpu + the nvidia-*-cu12 CUDA
# libs, so the default download already includes the full GPU stack (~1.5 GB).
# The libs only ship as x86_64 wheels — GPU is only meaningful on linux_x86_64.
#
# Examples:
#   ./prepare_offline.sh                                   # GPU build, py3.12 x86_64
#   PY_VERSION=311 ./prepare_offline.sh                    # GPU build, py3.11 x86_64
#   ./prepare_offline.sh requirements.txt auto             # whatever the current machine is

set -euo pipefail
# this script lives in offline/ — operates on project root
cd "$(dirname "$0")/.."

REQ_FILE="${1:-backend/requirements.txt}"
PLATFORM="${2:-linux_x86_64}"
PY_VERSION="${PY_VERSION:-312}"   # default: 3.12 — override with `PY_VERSION=311 ./prepare_offline.sh`
WHEEL_DIR="offline/wheels"

if [ ! -f "$REQ_FILE" ]; then
    echo "ERROR: $REQ_FILE not found." >&2
    exit 1
fi

echo "→ Building offline wheel cache in $WHEEL_DIR/"
echo "  requirements: $REQ_FILE"
echo "  platform:     $PLATFORM"
echo "  python:       3.${PY_VERSION#3}"
rm -rf "$WHEEL_DIR"
mkdir -p "$WHEEL_DIR"

# Build the pip-download command.
# When PLATFORM=auto, omit --platform/--python-version so pip uses the current
# machine's compatibility tags — the simplest, most reliable case.
# When PLATFORM is explicit, pass the full manylinux family so we match
# modern wheels (pandas, numpy, etc. ship as manylinux_2_17 / manylinux2014).
PIP_ARGS=(
    --dest "$WHEEL_DIR"
    --only-binary=:all:
    -r "$REQ_FILE"
)
if [ "$PLATFORM" != "auto" ]; then
    case "$PLATFORM" in
        linux_x86_64)
            # Declare a broad set of manylinux tags so we pick up modern wheels
            # (e.g. pymediainfo ships as manylinux_2_27, torch sometimes 2_28).
            # Order doesn't matter; pip considers all of them as compatible.
            PIP_ARGS+=(
                --platform manylinux_2_34_x86_64
                --platform manylinux_2_31_x86_64
                --platform manylinux_2_28_x86_64
                --platform manylinux_2_27_x86_64
                --platform manylinux_2_24_x86_64
                --platform manylinux_2_17_x86_64
                --platform manylinux2014_x86_64
                --platform manylinux2010_x86_64
                --platform manylinux1_x86_64
                --platform linux_x86_64
            ) ;;
        linux_aarch64)
            PIP_ARGS+=(
                --platform manylinux_2_34_aarch64
                --platform manylinux_2_31_aarch64
                --platform manylinux_2_28_aarch64
                --platform manylinux_2_27_aarch64
                --platform manylinux_2_17_aarch64
                --platform manylinux2014_aarch64
                --platform linux_aarch64
            ) ;;
        *)
            PIP_ARGS+=( --platform "$PLATFORM" ) ;;
    esac
    PIP_ARGS+=( --python-version "$PY_VERSION" --implementation cp )
fi

python3 -m pip download "${PIP_ARGS[@]}"

# Also bundle pip/setuptools/wheel themselves. The offline setup.sh runs
# pip-X.Y.whl as a zipapp to bootstrap pip into the venv — this sidesteps
# `ensurepip`, which on Debian/Ubuntu is only available when the
# `python3.X-venv` apt package is installed (often not the case on
# air-gapped machines). So we always need a pip wheel in wheels/.
#
# These are pure-Python (py3-none-any), so no platform/python-version flags.
echo
echo "→ Adding pip / setuptools / wheel to the cache (for offline venv bootstrap)"
python3 -m pip download \
    --dest "$WHEEL_DIR" \
    --only-binary=:all: \
    pip setuptools wheel

# Keep a copy of the active requirements file next to the wheels so setup.sh
# knows which one to use on the offline machine.
cp "$REQ_FILE" "$WHEEL_DIR/active-requirements.txt"

# Some packages (notably ultralytics) try to fetch model files at runtime.
# We already ship code_proc/*.pt so this is just a belt-and-suspenders check.
echo
echo "→ Confirming pre-downloaded model weights:"
ls -lh backend/models/*.onnx | awk '{print "    " $9, "(" $5 ")"}'

# Final size
echo
echo "→ Wheel cache ready:"
du -sh "$WHEEL_DIR"
ls "$WHEEL_DIR" | wc -l | xargs printf '  %s wheels\n'

echo
echo "✓ Ready to transfer. tar the whole folder and copy to the offline machine."
echo "  Example: cd .. && tar --exclude='face-masking-studio/backend/.venv' -czf face-masking-studio-offline.tar.gz face-masking-studio/"
