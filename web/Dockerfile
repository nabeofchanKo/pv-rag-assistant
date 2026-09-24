# syntax=docker/dockerfile:1
#
# PV Triage Assistant — web (Next.js BFF + UI) container image.
#
# Build context is web/:
#   docker build -t pv-rag-assistant-web:local ./web
#
# Three stages: install deps, build, then a slim runtime that carries only the
# standalone server output (no node_modules, no source).

# ---- Stage 1: deps ----
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- Stage 2: build ----
FROM node:24-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ---- Stage 3: runtime ----
FROM node:24-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Dedicated non-root runtime user.
RUN addgroup -g 1001 nodejs && adduser -u 1001 -G nodejs -S nextjs

# `output: "standalone"` bundles the server plus only the dependencies it
# actually uses; static/ and public/ are not included in that bundle, so they
# are copied alongside it.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["node", "-e", "fetch('http://localhost:3000/triage').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]

CMD ["node", "server.js"]
