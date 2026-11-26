import math

import torch
from torch import nn

from training.models.unet import SegmentationOutput, UNet


class SliceContextFusion(nn.Module):
    def __init__(self, feature_channels: int) -> None:
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(1, feature_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(feature_channels),
            nn.ReLU(inplace=True),
        )
        self.query = nn.Linear(feature_channels, feature_channels, bias=False)
        self.key = nn.Linear(feature_channels, feature_channels, bias=False)
        self.value = nn.Conv2d(feature_channels, feature_channels, 1, bias=False)
        self.project = nn.Conv2d(feature_channels, 1, 1)

    def forward(self, image: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if image.ndim == 4:
            image = image.unsqueeze(2)
        if image.ndim != 5 or image.shape[2] != 1 or image.shape[1] % 2 != 1:
            raise ValueError("Context input must have shape [B,S,1,H,W] with odd S.")
        batch, slices, _, height, width = image.shape
        center = slices // 2
        features = self.stem(image.reshape(batch * slices, 1, height, width))
        features = features.reshape(batch, slices, -1, height, width)
        pooled = features.mean(dim=(-2, -1))
        query = self.query(pooled[:, center]).unsqueeze(1)
        keys = self.key(pooled)
        scores = (query * keys).sum(dim=-1) / math.sqrt(features.shape[2])
        weights = torch.softmax(scores, dim=1)
        values = self.value(features.reshape(batch * slices, -1, height, width))
        values = values.reshape(batch, slices, -1, height, width)
        fused = (values * weights[:, :, None, None, None]).sum(dim=1) + features[:, center]
        center_image = image[:, center, 0]
        return self.project(fused) + center_image[:, None], weights


class SliceContextUNet(nn.Module):
    def __init__(self, backbone: UNet) -> None:
        super().__init__()
        if backbone.input_channels != 1:
            raise ValueError("Center-attention fusion requires a single-channel U-Net input.")
        self.backbone = backbone
        self.context_fusion = SliceContextFusion(backbone.channels[0])

    def forward(
        self, image: torch.Tensor, *, return_outputs: bool = False
    ) -> torch.Tensor | SegmentationOutput:
        fused, attention = self.context_fusion(image)
        output = self.backbone(fused, return_outputs=return_outputs)
        if not return_outputs:
            return output
        if not isinstance(output, SegmentationOutput):
            raise RuntimeError("The U-Net did not return the requested structured output.")
        return SegmentationOutput(
            output.segmentation_logits,
            output.aux_logits,
            output.boundary_logits,
            attention,
        )
