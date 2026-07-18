FROM python:3.13.13-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libmariadb-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install \
    torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --prefix=/install \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

FROM python:3.13.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmariadb3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

RUN find /usr/local/lib -type d \( -name "tests" -o -name "test" -o -name "__pycache__" \) -exec rm -rf {} + 2>/dev/null; \
    find /usr/local/lib -name "*.pyc" -delete 2>/dev/null; \
    find /usr/local/lib -name "*.pyi" -delete 2>/dev/null; \
    find /usr/local/lib -name "*.so" -exec strip --strip-unneeded {} + 2>/dev/null; \
    true

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/

WORKDIR /

COPY . .

# defer embedding model download to runtime — saves ~500MB from image
# RUN python -c "from main.utils.models.loader import getEmbeddingModel; getEmbeddingModel()"

CMD ["python", "run.py"]
