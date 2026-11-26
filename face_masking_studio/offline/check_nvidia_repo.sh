#!/usr/bin/env bash
# Checks NVIDIA drivers and kernel headers available in Ubuntu 24.04.
# Runs inside a Docker container to remain independent of the host machine state.
#
# Usage:
#   sudo ./check_nvidia_repo.sh [kernel_version]
#
# Example:
#   sudo ./check_nvidia_repo.sh 6.17.0-19-generic

set -euo pipefail

KERNEL_VER="${1:-6.17.0-19-generic}"

cat > /tmp/_check_inside.sh <<INNER
#!/bin/bash
set -e
cat > /etc/apt/sources.list <<SRC
deb http://archive.ubuntu.com/ubuntu/ noble main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu/ noble-updates main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu/ noble-backports main restricted universe multiverse
deb http://security.ubuntu.com/ubuntu/ noble-security main restricted universe multiverse
SRC
rm -f /etc/apt/sources.list.d/*
apt-get update -qq
echo "--- NVIDIA drivers (meta-packages) ---"
apt-cache search '^nvidia-driver-[0-9]' | sort
echo
echo "--- NVIDIA DKMS ---"
apt-cache search '^nvidia-dkms-[0-9]' | sort
echo
echo "--- Kernel headers for $KERNEL_VER ---"
apt-cache show linux-headers-$KERNEL_VER 2>/dev/null | head -3 || echo "NOT available"
echo
echo "--- linux-headers-generic (alternative) ---"
apt-cache show linux-headers-generic 2>/dev/null | head -3 || echo "NOT available"
INNER

chmod +x /tmp/_check_inside.sh
docker run --rm -v /tmp/_check_inside.sh:/check.sh ubuntu:24.04 bash /check.sh
