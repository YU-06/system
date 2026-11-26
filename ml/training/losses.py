import torch
from torch import nn


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
