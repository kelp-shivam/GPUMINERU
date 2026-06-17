from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_KEY: str
    API_KEY_NAME: str = "X-API-Key"

    UPLOAD_DIR: str = "/app/data/uploads"
    OUTPUT_DIR: str = "/app/data/outputs"
    MODELS_DIR: str = "/root/models"

    # MinerU parse settings — hybrid = pipeline layout + VLM verification
    MINERU_DEVICE: str = "cuda"
    MINERU_LANG: str = "auto"
    MINERU_FORCE_OCR: bool = True
    MINERU_BACKEND: str = "hybrid"
    MINERU_EFFORT: str = "high"

    # L4 46GB: model loads ~20-28GB → 2 safe parallel inference threads
    # Increase to 3 only if you've profiled peak VRAM < 42GB
    PARALLEL_WORKERS: int = 2

    # Enable CUDA MPS for true GPU time-slicing across parallel workers
    # Run `scripts/enable_mps.sh` on host before starting container
    CUDA_MPS_ENABLE: bool = True

    MAX_UPLOAD_MB: int = 500
    JOB_TTL_SECONDS: int = 3600

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    class Config:
        env_file = ".env"


settings = Settings()
