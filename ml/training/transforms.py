from dataclasses import dataclass

import torch


@dataclass(frozen=True)
class SynchronizedTransforms:
    horizontal_flip_probability: float = 0.5
    vertical_flip_probability: float = 0.5
    rotate_90: bool = True
    intensity_augmentation: bool = False
    intensity_transform_mode: str = "synchronized"
    intensity_strength: float = 0.05

    def __post_init__(self) -> None:
        if (
            not 0 <= self.horizontal_flip_probability <= 1
            or not 0 <= self.vertical_flip_probability <= 1
        ):
            raise ValueError("Flip probabilities must be in [0, 1].")
        if self.intensity_transform_mode not in {"synchronized", "independent"}:
            raise ValueError("Intensity transform mode must be synchronized or independent.")
        if not 0 <= self.intensity_strength <= 1:
            raise ValueError("Intensity strength must be in [0, 1].")

    def __call__(
        self, image: torch.Tensor, mask: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        if (
            image.ndim != 3
            or mask.ndim != 3
            or image.shape[-2:] != mask.shape[-2:]
            or mask.shape[0] != 1
        ):
            raise ValueError("Image channels and a single-channel mask must share spatial shape.")
        if torch.rand(()).item() < self.horizontal_flip_probability:
            image, mask = torch.flip(image, [-1]), torch.flip(mask, [-1])
        if torch.rand(()).item() < self.vertical_flip_probability:
            image, mask = torch.flip(image, [-2]), torch.flip(mask, [-2])
        if self.rotate_90:
            rotations = int(torch.randint(0, 4, ()).item())
            image = torch.rot90(image, rotations, [-2, -1])
            mask = torch.rot90(mask, rotations, [-2, -1])
        if self.intensity_augmentation:
            channels = image.shape[0] if self.intensity_transform_mode == "independent" else 1
            scale = torch.empty((channels, 1, 1), dtype=image.dtype, device=image.device)
            scale.uniform_(1 - self.intensity_strength, 1 + self.intensity_strength)
            offset = torch.empty((channels, 1, 1), dtype=image.dtype, device=image.device)
            offset.uniform_(-self.intensity_strength, self.intensity_strength)
            image = image * scale + offset
        return image.contiguous(), mask.contiguous()
