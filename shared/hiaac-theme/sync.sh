#!/usr/bin/env bash
# Copy the shared web theme into every tool so each one stays runnable on its own.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/shared/hiaac-theme/web"
TARGETS=(
  "face_masking_studio/frontend/hiaac"
  "server-processing/preprocessor/public/hiaac"
  "annotation_interface/assets/hiaac"
  "viewer_interface/assets/hiaac"
)
for t in "${TARGETS[@]}"; do
  rm -rf "$ROOT/$t"
  mkdir -p "$ROOT/$t"
  cp -r "$SRC/." "$ROOT/$t/"
  echo "synced -> $t"
done
