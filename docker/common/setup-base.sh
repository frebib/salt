#!/bin/bash
set -eux

CTX_DIR="${CTX_DIR:-/ctx}"
PKG_DIR="${PKG_DIR:-$CTX_DIR}"

if [ $# -lt 1 ]; then
	echo "Usage: $0 <debian release> [salt package version]"
	exit 1
fi

debian_release="$1"
shift

if [ $# -ge 1 ]; then
	pkg_version="$1"
	shift
fi
if [ -z "${pkg_version-}" ]; then
	if [ -r "${CTX_DIR}/DEB_VERSION" ]; then
		pkg_version="$(cat "${CTX_DIR}/DEB_VERSION")"
	else
		>&2 printf "No VERSION build-arg specified and no VERSION file found in %s/DEB_VERSION" "${CTX_DIR}"
		exit 1
	fi
fi

# Install build-time dependencies
apt-get update
apt-get install -y --no-install-recommends \
	dpkg-dev

# Debian-ify the package version
pkg_version="${pkg_version/.g/~g}"

packages=(
	"${PKG_DIR}/salt-common_${pkg_version}_all.deb"
	gokey

	python3-gnupg
	python3-netaddr
	python3-cryptography
	python3-cffi
	python3-cffi-backend
)

if [ "$(dpkg-architecture -qDEB_HOST_ARCH)" = "amd64" ] ; then
	packages+=(python3-m2crypto-fips)
fi

# Install run-time dependencies
apt-get install -y --no-install-recommends \
	"${packages[@]}" "${@}"

# Remove build-time dependencies and unnecessary packages
apt-get purge -y dpkg-dev
apt-get autoremove -y
