FROM node:24.12.0-bookworm-slim@sha256:6d8047885b91084ceff824c02950be237dafcbfd3d1b6e69d49c919868e806be

ARG CONNECTOR_RELEASE=0.1.3-dev
ARG CONNECTOR_REVISION=unknown
ARG CONNECTOR_BUILD_DATE=unknown
LABEL org.opencontainers.image.title="ERPNext WhatsApp Connection Gateway by TNGSol.com" \
      org.opencontainers.image.source="https://github.com/webmoxter/erpnext-whatsapp-connection" \
      org.opencontainers.image.revision="${CONNECTOR_REVISION}" \
      org.opencontainers.image.version="${CONNECTOR_RELEASE}" \
      org.opencontainers.image.created="${CONNECTOR_BUILD_DATE}"

WORKDIR /srv/erpnext-whatsapp
COPY package.json pnpm-lock.yaml ./
RUN corepack enable \
    && corepack prepare pnpm@11.19.0 --activate \
    && pnpm install --prod --frozen-lockfile --ignore-scripts \
    && pnpm store prune
COPY --chown=node:node src ./src

USER node
ENV NODE_ENV=production
CMD ["node", "src/server.mjs"]
