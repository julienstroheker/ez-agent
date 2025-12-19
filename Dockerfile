# EZ-Agent Base Image
# Multi-stage build optimized for production deployments
# Use this as a base image and mount your agent.yaml configuration

# =============================================================================
# Stage 1: Builder
# =============================================================================
FROM mcr.microsoft.com/azurelinux/base/python:3.12 AS builder

WORKDIR /build

# Install build dependencies (minimal set for Python packages)
RUN tdnf install -y --setopt=install_weak_deps=False \
    build-essential \
    gcc \
    && tdnf clean all

# Create virtual environment in a predictable location
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip and install wheel for faster builds
RUN pip install --no-cache-dir --upgrade pip wheel

# Copy only what's needed for installation
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install the package
RUN pip install --no-cache-dir . && \
    # Remove unnecessary files to reduce image size
    find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/venv -type f -name "*.pyc" -delete 2>/dev/null || true && \
    find /opt/venv -type f -name "*.pyo" -delete 2>/dev/null || true

# =============================================================================
# Stage 2: Runtime (Distroless)
# =============================================================================
FROM mcr.microsoft.com/azurelinux/distroless/python:3.12 AS runtime

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Disable pip version check in runtime
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory for agent configurations
WORKDIR /app

# Default port for HTTP mode
EXPOSE 8000

# Distroless images run as non-root by default (uid 65532)
# No need for USER directive - already non-root

# Entry point - expects agent.yaml to be mounted at /app/agent.yaml
# Override CMD in derived images or at runtime
ENTRYPOINT ["/opt/venv/bin/ezagent"]
CMD ["run", "-c", "/app/agent.yaml", "-m", "http", "--host", "0.0.0.0", "--port", "8000"]

# =============================================================================
# Labels (OCI Image Spec)
# =============================================================================
LABEL org.opencontainers.image.title="EZ-Agent" \
      org.opencontainers.image.description="AI Agent Framework - Base Image" \
      org.opencontainers.image.source="https://github.com/julienstroheker/ez-agent" \
      org.opencontainers.image.vendor="EZ-Agent" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="mcr.microsoft.com/azurelinux/distroless/python:3.12"
