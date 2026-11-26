#!/usr/bin/env bash
# Run this on a machine WITH internet, same Ubuntu version+arch as the offline target.
# Downloads ffmpeg + its dependencies as .deb files into offline/apt_debs/
# so the offline machine can install them without network.
#
# Usage:
#   ./prepare_offline_apt.sh                # downloads the default set
#   ./prepare_offline_apt.sh pkg1 pkg2 ...  # downloads a custom set
#
# On the offline machine:
#   sudo dpkg -i offline/apt_debs/*.deb
#   # if dpkg complains about missing deps already installed elsewhere:
#   sudo apt-get install -f --no-download

set -euo pipefail
# this script lives in offline/ — operates on project root
cd "$(dirname "$0")/.."

DEB_DIR="offline/apt_debs"
PACKAGES=("$@")
if [ ${#PACKAGES[@]} -eq 0 ]; then
    PACKAGES=(ffmpeg)
fi

echo "Target Ubuntu: $(lsb_release -ds 2>/dev/null || echo unknown)"
echo "Architecture:  $(dpkg --print-architecture)"
echo "Packages:      ${PACKAGES[*]}"
echo

# Make sure apt has fresh index — otherwise some deps may not be resolvable.
echo "Refreshing apt index (may need sudo)..."
sudo apt-get update -qq

rm -rf "$DEB_DIR"
mkdir -p "$DEB_DIR"

# Recursively resolve all dependencies. apt-cache depends doesn't recurse on
# its own, so use --recurse. We exclude virtual packages (lines starting
# with "<") and de-dupe.
ALL_DEPS="$(
    apt-cache depends --recurse \
        --no-recommends --no-suggests --no-conflicts \
        --no-breaks --no-replaces --no-enhances --no-pre-depends \
        "${PACKAGES[@]}" \
    | awk '/^\w/ {print $1}' \
    | sort -u
)"

# Download every .deb (including the packages themselves). cd into the dir
# because apt-get download writes to CWD.
echo
echo "Downloading $(echo "$ALL_DEPS" | wc -l) packages..."
(
    cd "$DEB_DIR"
    # shellcheck disable=SC2086
    apt-get download $ALL_DEPS
)

echo
echo "$DEB_DIR is ready ($(du -sh "$DEB_DIR" | cut -f1), $(ls "$DEB_DIR" | wc -l) .deb files)."
echo
echo "On the offline machine:"
echo "  sudo dpkg -i $DEB_DIR/*.deb"
echo "  # if anything is missing or held back:"
echo "  sudo apt-get install -f --no-download"
