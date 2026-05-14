# ── Build stage ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Instalar dependencias en capa separada (cache-friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────────
FROM python:3.12-slim

# Usuario no-root por seguridad
RUN useradd -m -u 1000 vigia
WORKDIR /app

# Copiar dependencias instaladas
COPY --from=builder /install /usr/local

# Copiar código fuente
COPY --chown=vigia:vigia . .

# Directorio de salida para archivos Excel
RUN mkdir -p /outputs && chown vigia:vigia /outputs

USER vigia

# Variables de entorno por defecto (sobreescribibles en Dokploy)
ENV PORT=8000 \
    HOST=0.0.0.0 \
    OUTPUT_DIR=/outputs \
    LOG_LEVEL=INFO \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Health check para Dokploy
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:${PORT}/health', timeout=5)" || exit 1

CMD ["python", "server.py"]
