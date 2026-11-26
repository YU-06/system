from pathlib import Path

import numpy as np
import pytest
import torch
from training.experiment_protocol import (
    apply_ablation_condition,
    assert_ablation_matrix_differences,
    load_ablation_matrix,
)
from training.losses import BoundaryDeepSupervisionLoss, boundary_target
from training.models import AttentionUNet, build_model
from training.preprocessing import context_slice_indices
from training.protocol import load_config
from training.reconstruct_volume import patient_spatial_metrics
from training.transforms import SynchronizedTransforms
from training.uncertainty import (
    brats_retention_metrics,
    calibration_metrics,
    ensemble_probabilities,
    uncertainty_to_uint8,
)


@pytest.mark.parametrize(
    ("center", "depth", "expected"),
    [(0, 3, (0, 0, 1)), (2, 3, (1, 2, 2)), (0, 1, (0, 0, 0))],
)
def test_context_window_clamps_at_volume_boundaries(center, depth, expected):
    assert context_slice_indices(center, depth, 3) == expected


@pytest.mark.parametrize("context_slices", [1, 3])
def test_context_models_accept_single_and_three_slice_inputs(context_slices):
    torch.manual_seed(7)
    model = build_model(
        "AttentionUNet",
        [2, 4, 8, 16, 32],
        input_mode="2p5d",
        context_slices=context_slices,
        slice_fusion="center_attention",
    ).eval()
    with torch.inference_mode():
        logits = model(torch.randn(1, context_slices, 32, 32))
    assert logits.shape == (1, 1, 32, 32)
    if context_slices == 1:
        assert isinstance(model, AttentionUNet)


def test_center_attention_weights_normalize_and_backpropagate():
    model = build_model(
        "AttentionUNet",
        [2, 4, 8, 16, 32],
        input_mode="2p5d",
        context_slices=3,
        slice_fusion="center_attention",
        boundary_head=True,
        deep_supervision=True,
    )
    image = torch.randn(2, 3, 32, 32, requires_grad=True)
    output = model(image, return_outputs=True)
    assert output.segmentation_logits.shape == (2, 1, 32, 32)
    assert output.aux_logits is not None and output.aux_logits.shape == (2, 1, 32, 32)
    assert output.boundary_logits is not None and output.boundary_logits.shape == (2, 1, 32, 32)
    assert output.slice_attention is not None
    assert torch.allclose(output.slice_attention.sum(1), torch.ones(2))
    output.segmentation_logits.mean().backward()
    assert image.grad is not None and torch.isfinite(image.grad).all()
    assert model.context_fusion.query.weight.grad is not None


def test_spatial_augmentation_is_shared_across_context_channels():
    torch.manual_seed(19)
    mask = torch.zeros(1, 16, 16)
    mask[:, 3:8, 5:9] = 1
    image = mask.repeat(3, 1, 1)
    transformed, target = SynchronizedTransforms()(image, mask)
    assert torch.equal(transformed[0], transformed[1])
    assert torch.equal(transformed[1], transformed[2])
    assert torch.equal(transformed[1], target[0])


def test_boundary_target_and_combined_loss_are_finite_for_empty_and_single_voxel_masks():
    empty = torch.zeros(1, 1, 9, 9)
    single = empty.clone()
    single[:, :, 4, 4] = 1
    assert boundary_target(empty).count_nonzero() == 0
    assert boundary_target(single).count_nonzero() == 9

    empty = torch.zeros(1, 1, 32, 32)
    single = empty.clone()
    single[:, :, 16, 16] = 1
    model = build_model(
        "UNet",
        [2, 4, 8, 16, 32],
        boundary_head=True,
        deep_supervision=True,
    )
    criterion = BoundaryDeepSupervisionLoss()
    for target in (empty, single, torch.ones_like(single)):
        output = model(torch.randn(1, 1, 32, 32), return_outputs=True)
        losses = criterion(output, target)
        assert torch.isfinite(losses.total)
        losses.total.backward()


def test_legacy_2d_model_weights_load_strictly_without_new_parameters():
    torch.manual_seed(41)
    old_model = AttentionUNet([2, 4, 8, 16, 32])
    state = old_model.state_dict()
    new_model = build_model("AttentionUNet", [2, 4, 8, 16, 32])
    new_model.load_state_dict(state, strict=True)
    assert set(new_model.state_dict()) == set(state)


def test_ensemble_uses_probability_mean_variance_entropy_and_bounded_uint8():
    first = np.full((2, 2), 0.25, dtype=np.float32)
    second = np.full((2, 2), 0.75, dtype=np.float32)
    result = ensemble_probabilities([first, second], 0.5)
    assert np.all(result.mean_probability == 0.5)
    assert np.all(result.binary_prediction == 1)
    assert np.allclose(result.predictive_entropy, 1.0)
    assert result.model_variance is not None
    assert np.allclose(result.model_variance, 0.0625)
    assert np.all(uncertainty_to_uint8(result.predictive_entropy, 1.0) == 100)
    single = ensemble_probabilities([first], 0.5)
    assert single.model_variance is None


def test_uncertainty_retention_keeps_selective_metrics_separate():
    prediction = np.array([1, 1, 1, 0], dtype=np.uint8)
    truth = np.array([1, 1, 0, 0], dtype=np.uint8)
    uncertainty = np.array([0, 100, 100, 0], dtype=np.float32)
    result = brats_retention_metrics(prediction, truth, uncertainty, (0, 100))
    assert result[0]["coverage"] == 0.5
    assert result[0]["retained_voxel_dice"] == 1
    assert result[0]["filtered_true_positive"] == 1
    assert result[0]["filtered_true_negative"] == 0
    no_coverage = brats_retention_metrics(
        np.zeros(2, dtype=np.uint8),
        np.zeros(2, dtype=np.uint8),
        np.full(2, 100, dtype=np.float32),
        (0,),
    )
    assert no_coverage[0]["coverage"] == 0
    assert no_coverage[0]["retained_voxel_dice"] is None


def test_calibration_metrics_are_defined_for_errors_and_single_class_edges():
    probability = np.array([0.8, 0.7, 0.2, 0.3], dtype=np.float32)
    expected = np.array([1, 0, 0, 1], dtype=np.uint8)
    uncertainty = np.array([0, 100, 0, 100], dtype=np.float32)
    result = calibration_metrics(probability, expected, uncertainty, bins=5)
    assert result["brier_score"] == pytest.approx(0.265)
    assert result["uncertainty_error_auroc"] == 1
    assert result["uncertainty_error_auprc"] == 1
    perfect_only = calibration_metrics(
        np.array([0.9], dtype=np.float32),
        np.array([1], dtype=np.uint8),
        np.array([0], dtype=np.float32),
    )
    assert perfect_only["uncertainty_error_auroc"] is None
    assert perfect_only["uncertainty_error_auprc"] is None


def test_surface_and_volume_metrics_require_trusted_geometry():
    affine = np.diag([1.0, 2.0, 3.0, 1.0])
    mask = np.zeros((5, 5, 5), dtype=np.uint8)
    mask[2, 2, 2] = 1
    result = patient_spatial_metrics(
        mask, mask, (1.0, 2.0, 3.0), "mm", affine, 1, affine, 1, affine
    )
    assert result["predicted_lesion_volume_mm3"] == 6
    assert result["ground_truth_lesion_volume_mm3"] == 6
    assert result["hd95_mm"] == result["assd_mm"] == 0

    empty = patient_spatial_metrics(
        np.zeros_like(mask),
        np.zeros_like(mask),
        (1.0, 2.0, 3.0),
        "mm",
        affine,
        1,
        affine,
        1,
        affine,
    )
    assert empty["hd95_mm"] is None
    assert empty["spatial_status"] == "NotRun_undefined_empty_surface"
    unknown_units = patient_spatial_metrics(
        mask, mask, (1.0, 2.0, 3.0), "unknown", affine, 1, affine, 1, affine
    )
    assert unknown_units["predicted_lesion_volume_mm3"] is None


def test_preregistered_ablation_matrix_only_varies_declared_components():
    matrix = load_ablation_matrix()
    config = load_config(Path("ml/configs/baseline.yaml"))
    assert_ablation_matrix_differences(config, matrix, 17)
    assert apply_ablation_condition(config, matrix, "A3").input_mode == "2p5d"


def test_invalid_even_context_is_rejected():
    with pytest.raises(ValueError, match="odd"):
        build_model(
            "UNet",
            [2, 4, 8, 16, 32],
            input_mode="2p5d",
            context_slices=2,
            slice_fusion="center_attention",
        )
