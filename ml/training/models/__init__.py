from collections.abc import Sequence
from typing import Literal

from torch import nn

from training.models.attention_unet import AttentionUNet
from training.models.slice_context import SliceContextUNet
from training.models.unet import SegmentationOutput, UNet


def build_model(
    architecture: Literal["UNet", "AttentionUNet"],
    channels: Sequence[int],
    *,
    input_mode: Literal["2d", "2p5d"] = "2d",
    context_slices: int = 3,
    slice_fusion: Literal["stack", "center_attention"] = "stack",
    boundary_head: bool = False,
    deep_supervision: bool = False,
) -> nn.Module:
    if context_slices < 1 or context_slices % 2 != 1:
        raise ValueError("Context slices must be an odd positive number.")
    if input_mode == "2d" and slice_fusion != "stack":
        raise ValueError("Center attention requires 2.5D input.")
    input_channels = context_slices if input_mode == "2p5d" and slice_fusion == "stack" else 1
    if architecture == "UNet":
        backbone = UNet(channels, input_channels, boundary_head, deep_supervision)
    else:
        backbone = AttentionUNet(channels, input_channels, boundary_head, deep_supervision)
    if input_mode == "2p5d" and slice_fusion == "center_attention" and context_slices > 1:
        return SliceContextUNet(backbone)
    return backbone


__all__ = ["UNet", "AttentionUNet", "SegmentationOutput", "SliceContextUNet", "build_model"]
