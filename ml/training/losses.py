from dataclasses import dataclass

import torch
from torch import nn
from torch.nn import functional as F

from training.models.unet import SegmentationOutput


class DiceLoss(nn.Module):
    def __init__(self, smoothing: float = 1e-6) -> None:
        super().__init__()
        if smoothing <= 0:
            raise ValueError("Dice smoothing must be positive.")
        self.smoothing = smoothing

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        if logits.shape != target.shape or logits.ndim != 4:
            raise ValueError("Logits and binary targets must have the same NCHW shape.")
        probability = logits.sigmoid().flatten(1)
        truth = target.flatten(1)
        intersection = (probability * truth).sum(1)
        dice = (2 * intersection + self.smoothing) / (
            probability.sum(1) + truth.sum(1) + self.smoothing
        )
        return 1 - dice.mean()


class BCEDiceLoss(nn.Module):
    def __init__(self, bce_weight: float = 0.5, smoothing: float = 1e-6) -> None:
        super().__init__()
        if not 0 <= bce_weight <= 1:
            raise ValueError("BCE weight must be in [0, 1].")
        self.bce_weight = bce_weight
        self.bce = nn.BCEWithLogitsLoss()
        self.dice = DiceLoss(smoothing)

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        return self.bce_weight * self.bce(logits, target) + (1 - self.bce_weight) * self.dice(
            logits, target
        )


def boundary_target(mask: torch.Tensor, radius: int = 1) -> torch.Tensor:
    if mask.ndim != 4 or mask.shape[1] != 1 or radius < 1:
        raise ValueError("Boundary targets require N1HW masks and a positive radius.")
    if not torch.isfinite(mask).all() or not torch.all((mask == 0) | (mask == 1)):
        raise ValueError("Boundary targets require finite binary masks.")
    padding = (radius, radius, radius, radius)
    dilated = F.max_pool2d(F.pad(mask, padding, mode="constant", value=0), 2 * radius + 1, 1)
    complement = 1 - mask
    eroded = 1 - F.max_pool2d(
        F.pad(complement, padding, mode="constant", value=1), 2 * radius + 1, 1
    )
    return (dilated - eroded).clamp_(0, 1)


@dataclass(frozen=True)
class LossBreakdown:
    total: torch.Tensor
    region: torch.Tensor
    auxiliary: torch.Tensor
    edge: torch.Tensor


class BoundaryDeepSupervisionLoss(nn.Module):
    def __init__(
        self,
        bce_weight: float = 0.5,
        smoothing: float = 1e-6,
        auxiliary_weight: float = 0.2,
        edge_weight: float = 0.1,
        edge_positive_weight: float = 2.0,
        boundary_radius: int = 1,
    ) -> None:
        super().__init__()
        if auxiliary_weight < 0 or edge_weight < 0 or edge_positive_weight <= 0:
            raise ValueError("Deep-supervision loss weights must be nonnegative and finite.")
        if boundary_radius < 1:
            raise ValueError("Boundary radius must be positive.")
        self.region_loss = BCEDiceLoss(bce_weight, smoothing)
        self.auxiliary_weight = auxiliary_weight
        self.edge_weight = edge_weight
        self.edge_positive_weight = edge_positive_weight
        self.boundary_radius = boundary_radius
        self.edge_loss = nn.BCEWithLogitsLoss(
            pos_weight=torch.tensor([edge_positive_weight], dtype=torch.float32)
        )

    def forward(
        self, output: torch.Tensor | SegmentationOutput, target: torch.Tensor
    ) -> LossBreakdown:
        if isinstance(output, torch.Tensor):
            segmentation_logits = output
            auxiliary_logits = None
            boundary_logits = None
        else:
            segmentation_logits = output.segmentation_logits
            auxiliary_logits = output.aux_logits
            boundary_logits = output.boundary_logits
        region = self.region_loss(segmentation_logits, target)
        zero = region.new_zeros(())
        auxiliary = (
            self.region_loss(auxiliary_logits, target) if auxiliary_logits is not None else zero
        )
        edge = zero
        if boundary_logits is not None:
            edge = self.edge_loss(boundary_logits, boundary_target(target, self.boundary_radius))
        total = region + self.auxiliary_weight * auxiliary + self.edge_weight * edge
        return LossBreakdown(total=total, region=region, auxiliary=auxiliary, edge=edge)
