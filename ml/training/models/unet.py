from collections.abc import Sequence
from dataclasses import dataclass

import torch
from torch import nn
from torch.nn import functional as F


class DoubleConv(nn.Sequential):
    def __init__(self, input_channels: int, output_channels: int) -> None:
        super().__init__(
            nn.Conv2d(input_channels, output_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(output_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(output_channels, output_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(output_channels),
            nn.ReLU(inplace=True),
        )


@dataclass(frozen=True)
class SegmentationOutput:
    segmentation_logits: torch.Tensor
    aux_logits: torch.Tensor | None = None
    boundary_logits: torch.Tensor | None = None
    slice_attention: torch.Tensor | None = None


class UNet(nn.Module):
    def __init__(
        self,
        channels: Sequence[int] = (32, 64, 128, 256, 512),
        input_channels: int = 1,
        boundary_head: bool = False,
        deep_supervision: bool = False,
    ) -> None:
        super().__init__()
        if len(channels) != 5 or any(channel < 1 for channel in channels) or input_channels < 1:
            raise ValueError("U-Net requires five positive channel widths.")
        self.channels = tuple(channels)
        self.input_channels = input_channels
        self.boundary_enabled = boundary_head
        self.deep_supervision_enabled = deep_supervision
        self.encoders = nn.ModuleList(
            [
                DoubleConv(input_channels if index == 0 else channels[index - 1], width)
                for index, width in enumerate(channels)
            ]
        )
        self.pool = nn.MaxPool2d(2)
        self.upconvolutions = nn.ModuleList(
            [
                nn.ConvTranspose2d(channels[index + 1], channels[index], 2, stride=2)
                for index in range(3, -1, -1)
            ]
        )
        self.decoders = nn.ModuleList(
            [DoubleConv(width * 2, width) for width in reversed(channels[:-1])]
        )
        self.output = nn.Conv2d(channels[0], 1, 1)
        self.auxiliary_output = nn.Conv2d(channels[-2], 1, 1) if deep_supervision else None
        self.boundary_output = nn.Conv2d(channels[0], 1, 1) if boundary_head else None

    def gate_skip(self, skip: torch.Tensor, decoder: torch.Tensor, index: int) -> torch.Tensor:
        return skip

    def forward(
        self, image: torch.Tensor, *, return_outputs: bool = False
    ) -> torch.Tensor | SegmentationOutput:
        if (
            image.ndim != 4
            or image.shape[1] != self.input_channels
            or image.shape[-2] % 16
            or image.shape[-1] % 16
        ):
            raise ValueError(
                "Input must be NCHW with configured channels and dimensions divisible by 16."
            )
        skips: list[torch.Tensor] = []
        current = image
        auxiliary_features: torch.Tensor | None = None
        for index, encoder in enumerate(self.encoders):
            if index:
                current = self.pool(current)
            current = encoder(current)
            if index < 4:
                skips.append(current)
        for index, (upconvolution, decoder) in enumerate(
            zip(self.upconvolutions, self.decoders, strict=True)
        ):
            current = upconvolution(current)
            skip = self.gate_skip(skips[-index - 1], current, index)
            current = decoder(torch.cat((skip, current), dim=1))
            if index == 0:
                auxiliary_features = current
        logits = self.output(current)
        if not return_outputs:
            return logits
        auxiliary_logits = None
        if self.auxiliary_output is not None:
            if auxiliary_features is None:
                raise RuntimeError("The configured auxiliary decoder feature was not produced.")
            auxiliary_logits = F.interpolate(
                self.auxiliary_output(auxiliary_features),
                size=image.shape[-2:],
                mode="bilinear",
                align_corners=False,
            )
        boundary_logits = (
            self.boundary_output(current) if self.boundary_output is not None else None
        )
        return SegmentationOutput(logits, auxiliary_logits, boundary_logits)
