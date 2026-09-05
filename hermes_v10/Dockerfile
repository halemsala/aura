# Hermes V10 Ultra — Production Container
FROM python:3.12-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends     gcc     libffi-dev     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage
FROM python:3.12-slim AS runtime

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends     curl     && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY . .

# Non-root user for security
RUN groupadd -r hermes && useradd -r -g hermes hermes     && chown -R hermes:hermes /app
USER hermes

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3     CMD curl -f http://localhost:8777/health || exit 1

EXPOSE 8777 8778

CMD ["python", "-m", "scripts.hermes_v10_chat_api"]
