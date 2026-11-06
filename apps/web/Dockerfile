FROM node:22.23.4-bookworm-slim AS build
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-fund
COPY apps/web/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.28-alpine AS runtime
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/brainseg/browser/ /usr/share/nginx/html/
USER 101
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=12 CMD wget -qO- http://127.0.0.1:8080/health || exit 1