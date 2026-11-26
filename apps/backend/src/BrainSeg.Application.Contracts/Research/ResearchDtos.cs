using Volo.Abp.Application.Dtos;

namespace BrainSeg.Research;

public sealed class BrainStudyDto : FullAuditedEntityDto<Guid>
{
    public string StudyNumber { get; set; } = string.Empty;
    public string Pseudonym { get; set; } = string.Empty;
    public string Modality { get; set; } = string.Empty;
    public string OriginalFileObjectKey { get; set; } = string.Empty;
    public string OriginalFileSha256 { get; set; } = string.Empty;
    public string? GroundTruthSha256 { get; set; }
    public bool HasGroundTruth { get; set; }
    public int Width { get; set; }
    public int Height { get; set; }
    public int SliceIndex { get; set; }
    public BrainStudyStatus Status { get; set; }
    public int JobRequestCount { get; set; }
    public string ConcurrencyStamp { get; set; } = string.Empty;
}

public sealed class SegmentationJobDto : FullAuditedEntityDto<Guid>
{
    public Guid StudyId { get; set; }
    public Guid ModelVersionId { get; set; }
    public string? InputSha256 { get; set; }
    public ModelArchitecture? Architecture { get; set; }
    public string? ModelSemanticVersion { get; set; }
    public string? PreprocessingVersion { get; set; }
    public string? WeightSha256 { get; set; }
    public int? InputSize { get; set; }
    public double? Threshold { get; set; }
    public Guid RequesterId { get; set; }
    public string IdempotencyKey { get; set; } = string.Empty;
    public SegmentationJobStatus Status { get; set; }
    public int Progress { get; set; }
    public string CorrelationId { get; set; } = string.Empty;
    public DateTimeOffset RequestedTime { get; set; }
    public DateTimeOffset? StartedTime { get; set; }
    public DateTimeOffset? CompletedTime { get; set; }
    public DateTimeOffset? LeaseExpiresAt { get; set; }
    public string? ErrorCode { get; set; }
    public string? ErrorMessage { get; set; }
    public int RetryCount { get; set; }
    public string ConcurrencyStamp { get; set; } = string.Empty;
}

public sealed class ModelVersionDto : FullAuditedEntityDto<Guid>
{
    public string Name { get; set; } = string.Empty;
    public ModelArchitecture Architecture { get; set; }
    public string SemanticVersion { get; set; } = string.Empty;
    public string PreprocessingVersion { get; set; } = string.Empty;
    public string WeightObjectKey { get; set; } = string.Empty;
    public string WeightSha256 { get; set; } = string.Empty;
    public int InputSize { get; set; }
    public double Threshold { get; set; }
    public string MetricsJson { get; set; } = string.Empty;
    public bool IsActive { get; set; }
    public bool IsDefault { get; set; }
    public DateTimeOffset? PublishedTime { get; set; }
    public string ConcurrencyStamp { get; set; } = string.Empty;
}

public sealed class SegmentationResultDto : FullAuditedEntityDto<Guid>
{
    public Guid JobId { get; set; }
    public string MaskObjectKey { get; set; } = string.Empty;
    public string? MaskSha256 { get; set; }
    public string? OverlayObjectKey { get; set; }
    public string? ContourObjectKey { get; set; }
    public string? ProbabilityObjectKey { get; set; }
    public string? ProbabilitySha256 { get; set; }
    public string? BoundaryObjectKey { get; set; }
    public string? BoundarySha256 { get; set; }
    public string? UncertaintyObjectKey { get; set; }
    public string? UncertaintySha256 { get; set; }
    public string? ModelVarianceObjectKey { get; set; }
    public string? ModelVarianceSha256 { get; set; }
    public string InputMode { get; set; } = "2d";
    public int ContextSlices { get; set; } = 1;
    public string SliceFusion { get; set; } = "stack";
    public bool BoundaryHead { get; set; }
    public bool DeepSupervision { get; set; }
    public string? MemberWeightHashesJson { get; set; }
    public int EnsembleSize { get; set; } = 1;
    public string? UncertaintyMethod { get; set; }
    public double? MeanUncertainty { get; set; }
    public double? P95Uncertainty { get; set; }
    public string? CalibrationMetricsJson { get; set; }
    public string? UncertaintyRetentionMetricsJson { get; set; }
    public string? RemotePredictionSha256 { get; set; }
    public string? GroundTruthSha256 { get; set; }
    public string? EvaluationProtocol { get; set; }
    public double? Dice { get; set; }
    public double? IoU { get; set; }
    public double? Precision { get; set; }
    public double? Recall { get; set; }
    public int TumorAreaPixels { get; set; }
    public double TumorAreaRatio { get; set; }
    public double InferenceMilliseconds { get; set; }
    public double PreprocessingMilliseconds { get; set; }
    public double PostprocessingMilliseconds { get; set; }
    public DateTimeOffset CreatedTime { get; set; }
    public string ConcurrencyStamp { get; set; } = string.Empty;
}

public sealed class ExperimentRunDto : FullAuditedEntityDto<Guid>
{
    public string ExperimentName { get; set; } = string.Empty;
    public string ConfigHash { get; set; } = string.Empty;
    public string GitCommit { get; set; } = string.Empty;
    public string DatasetSplitHash { get; set; } = string.Empty;
    public int RandomSeed { get; set; }
    public Guid ModelVersionId { get; set; }
    public string MetricsJson { get; set; } = string.Empty;
    public string ArtifactObjectKey { get; set; } = string.Empty;
    public DateTimeOffset CreatedTime { get; set; }
    public string ConcurrencyStamp { get; set; } = string.Empty;
}
