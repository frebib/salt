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

packages=(
	"${PKG_DIR}/salt-master_${pkg_version}_all.deb"
	"${PKG_DIR}/salt-api_${pkg_version}_all.deb"

	# salt-api requires cherrypy
	python3-cherrypy3
	python3-sentry-sdk
	python3-radix
	python3-jwt
	python3-yappi
	# EPT-1034: file:// transport adapter for SHR
	python3-requests-file
	# python3-prometheus-client is needed to run the 'master_metrics' engine
	# that provided Prometheus metrics for master (if enabled)
	python3-prometheus-client
	# Needed to communicate with Quicksilver over the memcache interface
	python3-pylibmc
	# if there's python3-setproctitle installed salt will set meaningful names on each
	# daemon process
	python3-setproctitle
	# required by tpm_attest external wheel module and cfvault
	python3-cryptography
	python3-cffi
	# need for salt-highstate-runner to communicate with etcd (Bandleader)
	python3-etcd3
	# GNUPG v2 has scalability issues, so we replace it with v1. It doesn't seem
	# to be possible to do it nicer than manually symlinking /usr/bin/gpg.
	# * https://jira.cfops.it/browse/CE-358
	# * https://jira.cfops.it/browse/EDGEPLAT-3476
	# * https://dev.gnupg.org/T5137
	gnupg1

	# Required to clone git+ssh repos
	git
	openssh-client

	# Salt complains if `ip` and `lspci` are unavailable.
	iproute2
	pciutils
	procps
	jq
	ripgrep
	less
	vim
	nano
)

apt-get update
apt-get install -y --no-install-recommends \
	"${packages[@]}" "${@}"

apt-get autoremove -y

# Fix up gpg.
rm -f /usr/bin/gpg
ln -s /usr/bin/gpg1 /usr/bin/gpg
