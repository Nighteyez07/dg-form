# ─── Builder stage ───────────────────────────────────────────────────────────
# Use the full slim image so we can install system libraries needed at build
# time by OpenCV (libGL) and MediaPipe (libglib2, libgthread, etc.).
FROM python:3.12-slim AS builder

# SECURITY: Prevent pip from caching packages to keep the layer lean and
# avoid inadvertently shipping stale/vulnerable cached wheels.
ENV PIP_NO_CACHE_DIR=1

WORKDIR /build

# Install system-level shared libraries required by OpenCV and MediaPipe.
# These are installed in the builder so that the compiled .so files are
# available when pip builds any native extensions; they will also be copied
# into the final stage below.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy only the dependency manifest first to exploit Docker layer caching:
# the pip install layer is rebuilt only when requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# ─── Final stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS final

# Improve Python behaviour inside containers:
#   PYTHONDONTWRITEBYTECODE – skip .pyc files; no need for them in a container.
#   PYTHONUNBUFFERED        – force stdout/stderr to be unbuffered so logs are
#                             emitted immediately without manual flush() calls.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib-cache

WORKDIR /app

# Re-install the same system runtime libraries needed by OpenCV/MediaPipe at
# run time. We only bring in the runtime libs (no -dev headers needed here).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        wget \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy the Python packages installed in the builder stage.
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source code.
COPY . .

# Pre-seed the MediaPipe Pose model so it is present before we drop privileges.
# Running this as root (build stage) ensures the download can write into site-packages.
RUN python -c "\
import mediapipe.python.solutions.pose as _p; \
_inst = _p.Pose(static_image_mode=True, model_complexity=0); \
_inst.close()" 2>/dev/null || true

# SECURITY: Run as a non-root user to limit blast radius if the process is
# compromised. A dedicated system account (no home dir, no login shell) is
# the minimal-privilege choice for a container service.
RUN groupadd --system appuser && useradd --system --gid appuser --create-home appuser

# Allow appuser to write the MediaPipe model cache if it was not pre-seeded.
RUN chown -R appuser:appuser /usr/local/lib/python3.12/site-packages/mediapipe/modules

# Create the tmpfs mount-point directory and hand ownership to appuser so
# the running process can write temp video files there.
# NOTE: docker-compose mounts a tmpfs at this path, so files never reach disk.
RUN mkdir -p /tmp/dg-form && chown appuser:appuser /tmp/dg-form

USER appuser

EXPOSE 8000

# TODO: Add --workers flag tuned to available CPU count before production.
# TODO: Enable --ssl-keyfile / --ssl-certfile or sit behind a TLS-terminating
#       reverse proxy before exposing this service publicly.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
