ARG DEBIAN_RELEASE=bullseye
ARG CLOUDFLARE_DOCKER_REGISTRY_HOST=docker-registry.cfdata.org
ARG BASE_IMAGE=${CLOUDFLARE_DOCKER_REGISTRY_HOST}/stash/cf/debian-images/${DEBIAN_RELEASE}/main:2022.8.0
FROM ${BASE_IMAGE}

ARG VERSION
ARG DEBIAN_RELEASE

RUN --mount=type=bind,target=/ctx \
    /ctx/docker/common/setup-base.sh "${DEBIAN_RELEASE}" "${VERSION}" && \
    /build/cleanup.sh
