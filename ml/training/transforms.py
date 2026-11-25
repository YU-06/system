from dataclasses import dataclass

import torch


@dataclass(frozen=True)
class SynchronizedTransforms:
    horizontal_flip_probability: float = 0.5
    vertical_flip_probability: float = 0.5
    rotate_90: bool = True

    def __post_init__(self) -> None:
        if (
            not 0 <= self.horizontal_flip_probability <= 1
            or not 0 <= self.vertical_flip_probability <= 1
        ):
            raise ValueError("Flip probabilities must be in [0, 1].")

    def __call__(
        self, image: torch.Tensor, mask: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        if image.shape != mask.shape or image.ndim != 3:
            raise ValueError("Image and mask must share one CHW shape.")
        if torch.rand(()).item() < self.horizontal_flip_probability:
            image, mask = torch.flip(image, [-1]), torch.flip(mask, [-1])
        if torch.rand(()).item() < self.vertical_flip_probability:
            image, mask = torch.flip(image, [-2]), torch.flip(mask, [-2])
        if self.rotate_90:
            rotations = int(torch.randint(0, 4, ()).item())
            image = torch.rot90(image, rotations, [-2, -1])
            mask = torch.rot90(mask, rotations, [-2, -1])
        return image.contiguous(), mask.contiguous()
