FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CUDA_HOME=/usr/local/cuda

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-dev python3-pip python3.11-venv \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    wget curl git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.11 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.11 /usr/bin/python

WORKDIR /app

# Install MinerU + API server deps
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124 && \
    pip install "mineru[all]==3.3.1" && \
    pip install fastapi uvicorn[standard] python-multipart aiofiles pydantic pydantic-settings aiofiles httpx

# App code
COPY app/ ./app/
COPY config/ ./config/

# MinerU model config
RUN mkdir -p /root && \
    cp /app/config/magic-pdf.json /root/magic-pdf.json

# Data dirs
RUN mkdir -p /app/data/uploads /app/data/outputs

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--timeout-keep-alive", "300"]
