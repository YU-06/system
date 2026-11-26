# ADR 0010: 2.5D Context, Boundary Supervision, and Uncertainty

Status: Accepted  
Scope: BraTS 2020, T2-FLAIR, axial Whole Tumor binary segmentation

**Disclaimer: For research and teaching only. Not a medical device; not for clinical diagnosis; no diagnostic, treatment, or prognosis advice.**

## Decision

Keep the existing 2D U-Net and Attention U-Net defaults and strict checkpoint layout compatible. The versioned `ml/configs/ablation_matrix.yaml` declares only four conditions:

| ID | Model |
| --- | --- |
| A0 | 2D U-Net |
| A1 | 2D Attention U-Net |
| A2 | A1 plus three-slice center-conditioned attention |
| A3 | A2 plus boundary head and deep-supervision head |

All conditions share the patient split and training protocol. Only architecture/gate, input mode/fusion, auxiliary heads, and run identity are declared as condition differences. The 2.5D sample uses clamped `[z-1,z,z+1]` T2-FLAIR channels and only the center-slice WT mask. No 3D convolution or transformer backbone is added.

The context module uses one shared convolutional stem for every slice, a center-derived query, per-slice key/value features, softmax over the slice dimension, and residual fusion with the center features. `context_slices=1` and default 2D settings leave the original path unchanged.

A3 uses the existing region loss plus `0.2 * auxiliary segmentation loss` and `0.1 * boundary loss`; the boundary target is generated from the center mask. Weights and boundary radius remain in YAML. Empty, full, and one-voxel masks are included in finite-loss tests.

Ensembles average member probabilities before applying the frozen threshold. Predictive entropy is mapped to uint8 [0,100] with a validation-frozen scale; member variance is emitted separately and is absent for a single checkpoint. Evaluation requires traceable GT and aligned probability/uncertainty artifacts before returning calibration and retained-voxel metrics. Missing GT means no accuracy or calibration values.

The inference manifest and response carry input mode, context/fusion, heads, member weight hashes, threshold, preprocessing version, and optional output object keys/hashes. ABP stores the output objects behind permission-checked downloads; Angular validates each artifact against the original grid before display.

## Consequences and limits

Old 2D configuration/checkpoints retain their previous forward path. Artifact fields added to PostgreSQL are nullable where historical results have no such outputs; new shape metadata has backward-compatible 2D defaults. Invalid or mismatched artifact geometry is rejected rather than resampled.

Synthetic fixtures exercise code paths only. No BraTS volumes, registered research weights, or GPU were available for this change; no training, formal test-set inference, clinical conclusion, performance claim, or Dice improvement is reported.

## Verification

Commands and true outcomes are recorded in [test report 0010](../test-reports/0010-2p5d-boundary-uncertainty.md). Parameter counts below are direct counts from the configured PyTorch modules, not trained-model results:

| Module | Parameters | Delta from legacy 2D Attention U-Net |
| --- | ---: | ---: |
| Legacy/A1 Attention U-Net | 7,850,709 | 0 |
| A2 2.5D center attention | 7,854,166 | +3,457 (+0.044%) |
| A3 boundary + deep supervision | 7,854,456 | +3,747 (+0.048%) |
