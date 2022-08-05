ARG DEBIAN_RELEASE=bullseye
FROM salt-${DEBIAN_RELEASE}-base

COPY ./docker/minion/rootfs /

ARG DEBIAN_RELEASE
RUN --mount=type=bind,target=/ctx \
    /ctx/docker/common/setup-minion.sh "${DEBIAN_RELEASE}" && \
    /build/cleanup.sh

ENTRYPOINT ["/run.sh"]
