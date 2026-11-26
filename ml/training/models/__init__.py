from training.models.attention_unet import AttentionUNet
from training.models.unet import UNet


def build_model(architecture: str, channels: list[int]) -> UNet:
    if architecture == "UNet":
        return UNet(channels)
    if architecture == "AttentionUNet":
        return AttentionUNet(channels)
    raise ValueError("Only UNet and AttentionUNet are allowed by the research protocol.")


__all__ = ["UNet", "AttentionUNet", "build_model"]
