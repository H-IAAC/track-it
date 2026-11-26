#!/usr/bin/env bash
# Same purpose as prepare_offline_apt.sh, but runs inside a Docker container
# of the requested Ubuntu version. Use this when the machine you are running
# on (the "internet machine") has a DIFFERENT Ubuntu version than the offline
# target — e.g. you are on 22.04 and the offline machine is 24.04.
#
# .deb files are version-specific: a 22.04 .deb usually won't install cleanly
# on 24.04 because libc/library SONAMEs change between releases.
#
# Usage:
#   ./prepare_offline_apt_docker.sh                  # default: ubuntu 24.04, ffmpeg
#   UBUNTU=22.04 ./prepare_offline_apt_docker.sh
#   ./prepare_offline_apt_docker.sh ffmpeg ffprobe libavcodec60
#
# Output:
#   offline/apt_debs_<version>/   (e.g. offline/apt_debs_24_04/)
# Copy that folder to the offline machine and:
#   sudo dpkg -i offline/apt_debs_24_04/*.deb
#   sudo apt-get install -f --no-download   # only if dpkg reports broken deps

set -euo pipefail
# this script lives in offline/ — operates on project root
cd "$(dirname "$0")/.."

UBUNTU="${UBUNTU:-24.04}"
PACKAGES=("$@")
if [ ${#PACKAGES[@]} -eq 0 ]; then
    PACKAGES=(ffmpeg)
fi
# Allow override so different package groups (ffmpeg vs nvidia-driver) can be
# saved into separate folders without overwriting each other.
DEB_DIR="${OUTPUT:-offline/apt_debs_${UBUNTU//./_}}"

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker is not installed on this machine." >&2
    echo "  Install it (e.g. 'sudo apt install docker.io' on Ubuntu/Debian)" >&2
    echo "  or run this script on another host that has docker." >&2
    echo "  Alternative: copy prepare_offline_apt.sh to any machine running" >&2
    echo "  Ubuntu $UBUNTU and execute it there directly (no docker needed)." >&2
    exit 1
fi

echo "Target Ubuntu:  $UBUNTU"
echo "Output folder:  $DEB_DIR/"
echo "Packages:       ${PACKAGES[*]}"
echo

rm -rf "$DEB_DIR"
mkdir -p "$DEB_DIR"

# We run as root inside the container (default), then chown back to the
# invoking user so the files are usable outside docker.
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
PKG_LIST="${PACKAGES[*]}"

docker run --rm -i \
    -v "$PWD/$DEB_DIR:/out" \
    -e PKG_LIST="$PKG_LIST" \
    -e HOST_UID="$HOST_UID" \
    -e HOST_GID="$HOST_GID" \
    "ubuntu:$UBUNTU" \
    bash -s <<'INNER_SCRIPT'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# Detect codename from /etc/os-release.
. /etc/os-release
CODENAME="$VERSION_CODENAME"
echo "Detected codename: $CODENAME"

# Wipe stock sources (which only enable main/restricted) and write a
# legacy-format sources.list with all four components.
rm -f /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list
cat > /etc/apt/sources.list <<EOF
deb http://archive.ubuntu.com/ubuntu/ $CODENAME main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu/ $CODENAME-updates main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu/ $CODENAME-backports main restricted universe multiverse
deb http://security.ubuntu.com/ubuntu/ $CODENAME-security main restricted universe multiverse
EOF

apt-get update -qq

cd /out

echo "Resolving recursive dependencies for: $PKG_LIST"

# Walk the dependency tree. apt-cache depends --recurse output format:
#   pkgname              ← lines we want (no leading whitespace)
#     Depends: other     ← indented lines we skip
# Use a portable regex (no \w gymnastics) and grep+cut, which avoids any
# awk-flavor differences inside the minimal Ubuntu image.
DEPS=$(apt-cache depends --recurse \
        --no-recommends --no-suggests --no-conflicts \
        --no-breaks --no-replaces --no-enhances --no-pre-depends \
        $PKG_LIST \
    | grep -E '^[^[:space:]<|]' \
    | sort -u)

COUNT=$(echo "$DEPS" | grep -c .)
if [ "$COUNT" -lt 10 ]; then
    echo "ERROR: only $COUNT package(s) resolved — sources or package names wrong." >&2
    echo "Raw apt-cache depends output (first 30 lines):" >&2
    apt-cache depends --recurse \
        --no-recommends --no-suggests --no-conflicts \
        --no-breaks --no-replaces --no-enhances --no-pre-depends \
        $PKG_LIST 2>&1 | head -30 >&2
    exit 1
fi

echo "Downloading $COUNT .deb files..."
echo "$DEPS" | xargs apt-get download
chown -R "$HOST_UID:$HOST_GID" /out
INNER_SCRIPT

echo
echo "Done. $DEB_DIR contains $(ls "$DEB_DIR" | wc -l) .deb files ($(du -sh "$DEB_DIR" | cut -f1))."
echo
echo "On the offline Ubuntu $UBUNTU machine:"
echo "  sudo dpkg -i $DEB_DIR/*.deb"
echo "  sudo apt-get install -f --no-download   # only if dpkg reports broken deps"
