from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ML_", env_file=".env", extra="ignore")
    model_path: Path | None = None
    model_sha256: str = ""
    model_version: str = "unpublished"
    preprocessing_version: Literal["flair-v1"] = "flair-v1"
    threshold: float = Field(default=0.5, gt=0, lt=1)
    input_size: Literal[256] = 256
    max_upload_bytes: int = Field(default=67108864, gt=0)
    max_decompressed_bytes: int = Field(default=134217728, gt=0)
    max_volume_voxels: int = Field(default=16777216, gt=0)
    request_timeout_seconds: float = Field(default=30.0, gt=0)
