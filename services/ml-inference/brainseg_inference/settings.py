from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ML_", env_file=".env", extra="ignore")

    model_manifest_path: Path | None = None
    object_storage_path: Path = Path("artifacts/inference-objects")
    max_upload_bytes: int = Field(default=67108864, gt=0, le=268435456)
    max_decompressed_bytes: int = Field(default=134217728, gt=0, le=536870912)
    max_volume_voxels: int = Field(default=16777216, gt=0, le=67108864)
    max_volume_dimension: int = Field(default=512, gt=0, le=2048)
    max_inference_batch_size: int = Field(default=16, gt=0, le=128)
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
