import pytest
import torch
from training.losses import BCEDiceLoss
from training.models import AttentionUNet, UNet
from training.transforms import SynchronizedTransforms


def test_image_and_mask_share_every_random_geometric_transform():
    torch.manual_seed(42)
    mask = torch.zeros(1, 16, 16)
    mask[:, 2:5, 7:10] = 1
    transform = SynchronizedTransforms()
    for _ in range(16):
        image, target = transform(mask.clone(), mask.clone())
        assert torch.equal(image, target)
        assert target.sum().item() == 9


def test_forced_flip_applies_identically_without_interpolation():
    mask = torch.arange(16).reshape(1, 4, 4).float()
    image, target = SynchronizedTransforms(1, 0, False)(mask.clone(), mask.clone())
    assert torch.equal(image, mask.flip(-1))
    assert torch.equal(image, target)


@pytest.mark.parametrize("model_type", [UNet, AttentionUNet])
def test_models_emit_single_channel_logits_at_the_fixed_size(model_type):
    torch.set_num_threads(2)
    model = model_type([2, 4, 8, 16, 32]).eval()
    with torch.inference_mode():
        output = model(torch.randn(1, 1, 256, 256))
    assert output.shape == (1, 1, 256, 256)
    assert torch.isfinite(output).all()


def test_attention_ablation_changes_only_gate_parameters():
    torch.manual_seed(42)
    baseline = UNet([2, 4, 8, 16, 32])
    torch.manual_seed(42)
    attention = AttentionUNet([2, 4, 8, 16, 32])
    baseline_parameters = dict(baseline.named_parameters())
    attention_parameters = dict(attention.named_parameters())
    for name, value in baseline_parameters.items():
        assert torch.equal(value, attention_parameters[name])
    extra = set(attention_parameters) - set(baseline_parameters)
    assert extra and all(name.startswith("attention_gates.") for name in extra)
    assert sum(value.numel() for value in attention.parameters()) > sum(
        value.numel() for value in baseline.parameters()
    )


def test_combined_loss_backpropagates_finite_gradients_for_empty_masks():
    logits = torch.zeros(2, 1, 32, 32, requires_grad=True)
    loss = BCEDiceLoss()(logits, torch.zeros_like(logits))
    loss.backward()
    assert torch.isfinite(loss)
    assert logits.grad is not None and torch.isfinite(logits.grad).all()
