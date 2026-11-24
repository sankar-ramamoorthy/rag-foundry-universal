# Foundry product frontend (issue #437, ADR-057): build static assets, serve
# them with a small non-root web server that also maps the product API paths
# to the orchestrator. Build context is ./frontend (it needs no shared code).

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Type-check, then build. Tests run in CI, not in the image build.
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
# The official image renders /etc/nginx/templates/*.template with the
# environment at start, so no service address is baked into the image.
# NGINX_ENTRYPOINT_LOCAL_RESOLVERS makes it export NGINX_LOCAL_RESOLVERS (the
# container's DNS resolvers) for the request-time upstream lookup.
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
ARG RELEASE_VERSION=dev
ENV APP_GIT_SHA=${GIT_SHA} \
    APP_BUILD_DATE=${BUILD_DATE} \
    APP_RELEASE_VERSION=${RELEASE_VERSION}

LABEL org.opencontainers.image.source="https://github.com/sankar-ramamoorthy/rag-foundry-universal" \
      org.opencontainers.image.title="foundry-frontend" \
      org.opencontainers.image.description="Foundry product frontend (static assets and same-origin product API mapping)" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.version="${RELEASE_VERSION}"

EXPOSE 8080
