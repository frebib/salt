#!/bin/bash
set -eux

CTX_DIR="${CTX_DIR:-/ctx}"
PKG_DIR="${PKG_DIR:-$CTX_DIR}"

if [ $# -lt 1 ]; then
	echo "Usage: $0 <debian release>"
	exit 1
fi

debian_release="$1"
shift

# Lock our sub packages to the same as common.
pkg_version=$(dpkg -l | grep -i salt-common | awk '{print $3;}')

# SRE-10046: Salt requires netstat for certain functions
# like network.default_gateway, so we pull in net-tools here.
# Upstream bug: https://github.com/saltstack/salt/issues/37851
#
# PLATOPS-4562: salt.dnsutils.A requires dig to exist if
# a nameserver argument is given; we do this early as part of
# the /etc/hosts rendering, thus is forced in the container.

packages=(
	"${PKG_DIR}/salt-minion_${pkg_version}_all.deb"

    dnsutils
    iproute2
    net-tools
    procps
    systemd
    systemd-sysv
    tpm2-emu
    tpm2-tools

    # These are only used in Salt TDE/Compose
    # Debugging tools for minion images
    python3-ipython
    python3-jupyter-console
)

# We also install TPM emulator and software to support salt TPM remote attestation in dev
apt-get update
apt-get install -y --no-install-recommends \
	"${packages[@]}" "${@}"

apt-get autoremove -y
