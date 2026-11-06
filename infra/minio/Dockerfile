FROM golang:1.24.9-bookworm AS build
ARG MINIO_RELEASE=RELEASE.2025-10-15T17-29-55Z
ARG MINIO_COMMIT=9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a
ENV CGO_ENABLED=0 GOTOOLCHAIN=local GOMAXPROCS=2
RUN git clone --depth 1 --branch "${MINIO_RELEASE}" https://github.com/minio/minio.git /source
WORKDIR /source
RUN test "$(git rev-parse HEAD)" = "${MINIO_COMMIT}" && go build -mod=readonly -trimpath -ldflags="-s -w" -o /out/minio .

FROM debian:bookworm-slim AS runtime
LABEL org.opencontainers.image.source="https://github.com/minio/minio" org.opencontainers.image.revision="9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a" org.opencontainers.image.licenses="AGPL-3.0-only"
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10001 --create-home minio && mkdir -p /data && chown 10001:10001 /data
COPY --from=build /out/minio /usr/local/bin/minio
COPY --from=build /source/LICENSE /usr/share/licenses/minio/LICENSE
USER 10001
EXPOSE 9000 9001
HEALTHCHECK --interval=5s --timeout=3s --retries=20 CMD curl -fsS http://127.0.0.1:9000/minio/health/live || exit 1
ENTRYPOINT ["/usr/local/bin/minio"]