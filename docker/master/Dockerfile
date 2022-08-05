ARG DEBIAN_RELEASE=bullseye
FROM salt-${DEBIAN_RELEASE}-base

COPY ./docker/master/rootfs /

ARG DEBIAN_RELEASE
RUN --mount=type=bind,target=/ctx \
    /ctx/docker/common/setup-master.sh "${DEBIAN_RELEASE}" && \
    /build/cleanup.sh

ENTRYPOINT ["/run.sh"]
