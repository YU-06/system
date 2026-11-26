from collections.abc import Sequence

import torch
from torch import nn


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


class UNet(nn.Module):
    def __init__(self, channels: Sequence[int] = (32, 64, 128, 256, 512)) -> None:
        super().__init__()
        if len(channels) != 5 or any(channel < 1 for channel in channels):
            raise ValueError("U-Net requires five positive channel widths.")
        self.channels = tuple(channels)
        self.encoders = nn.ModuleList(
            [
                DoubleConv(1 if index == 0 else channels[index - 1], width)
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

    def gate_skip(self, skip: torch.Tensor, decoder: torch.Tensor, index: int) -> torch.Tensor:
        return skip

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        if image.ndim != 4 or image.shape[1] != 1 or image.shape[-2] % 16 or image.shape[-1] % 16:
            raise ValueError("Input must be NCHW, single-modal, with dimensions divisible by 16.")
        skips: list[torch.Tensor] = []
        current = image
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
        return self.output(current)
