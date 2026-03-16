# ─── Builder stage ───────────────────────────────────────────────────────────
# node:22-alpine is the smallest official Node image that ships npm; alpine
# keeps the attack surface small during the build step.
FROM node:22-alpine AS builder

WORKDIR /app

# Copy only the dependency manifests first to exploit Docker layer caching.
COPY package.json package-lock.json ./

# `npm ci` reproduces the exact dependency tree recorded in package-lock.json;
# unlike `npm install` it fails on lock-file drift, making builds reproducible.
RUN npm ci

# Copy the rest of the source and produce the production bundle.
COPY . .
RUN npm run build


# ─── Final stage ─────────────────────────────────────────────────────────────
# nginx:1.27-alpine: pinned minor version for reproducibility.
# The alpine variant is ~8 MB and has no unnecessary tooling in production.
FROM nginx:1.27-alpine AS final

# SECURITY: Remove the default nginx config which listens on port 80 with a
# permissive server block; replace it entirely with our hardened config.
RUN rm /etc/nginx/conf.d/default.conf

# Copy the compiled SPA assets from the builder stage.
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy our custom nginx configuration (SPA routing + API proxy + headers).
COPY nginx.conf /etc/nginx/nginx.conf

# SECURITY: nginx by default runs the worker processes as the `nginx` user
# (UID 101); the master process must still start as root to bind port 80 but
# immediately drops privileges for workers. The USER directive here applies to
# any CMD/RUN after it; the actual privilege drop is managed by nginx itself
# via the `user nginx` directive inside nginx.conf.
# Port 80 requires binding as root, which is why we cannot switch to a fully
# non-root user at the Dockerfile level without remapping to an unprivileged
# port. A future improvement is to switch to port 8080 and use USER nginx here.
# TODO: Switch to an unprivileged port (e.g. 8080) and add `USER nginx` here
#       before production deployment behind a load-balancer that terminates TLS.

EXPOSE 80

# nginx is started by the default CMD inherited from the base image:
#   nginx -g 'daemon off;'
