from collections.abc import Sequence

import torch
from torch import nn

from training.models.unet import UNet


class AttentionGate(nn.Module):
    def __init__(self, channels: int) -> None:
        super().__init__()
        intermediate = max(1, channels // 2)
        self.skip_projection = nn.Sequential(
            nn.Conv2d(channels, intermediate, 1, bias=False), nn.BatchNorm2d(intermediate)
        )
        self.decoder_projection = nn.Sequential(
            nn.Conv2d(channels, intermediate, 1, bias=False), nn.BatchNorm2d(intermediate)
        )
        self.coefficient = nn.Sequential(
            nn.ReLU(inplace=False), nn.Conv2d(intermediate, 1, 1), nn.Sigmoid()
        )

    def forward(self, skip: torch.Tensor, decoder: torch.Tensor) -> torch.Tensor:
        coefficient = self.coefficient(
            self.skip_projection(skip) + self.decoder_projection(decoder)
        )
        return skip * coefficient


class AttentionUNet(UNet):
    def __init__(
        self,
        channels: Sequence[int] = (32, 64, 128, 256, 512),
        input_channels: int = 1,
        boundary_head: bool = False,
        deep_supervision: bool = False,
    ) -> None:
        super().__init__(channels, input_channels, boundary_head, deep_supervision)
        self.attention_gates = nn.ModuleList(
            [AttentionGate(width) for width in reversed(channels[:-1])]
        )

    def gate_skip(self, skip: torch.Tensor, decoder: torch.Tensor, index: int) -> torch.Tensor:
        return self.attention_gates[index](skip, decoder)
