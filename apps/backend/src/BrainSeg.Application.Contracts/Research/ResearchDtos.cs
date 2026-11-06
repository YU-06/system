using Volo.Abp.Application.Dtos;

namespace BrainSeg.Research;

public sealed class BrainStudyDto : FullAuditedEntityDto<Guid>
{
    public string StudyNumber { get; set; } = string.Empty;
    public string Pseudonym { get; set; } = string.Empty;
    public string Modality { get; set; } = string.Empty;
    public string OriginalFileObjectKey { get; set; } = string.Empty;
    public string OriginalFileSha256 { get; set; } = string.Empty;
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
    public Guid RequesterId { get; set; }
    public string IdempotencyKey { get; set; } = string.Empty;
    public SegmentationJobStatus Status { get; set; }
    public int Progress { get; set; }
    public string CorrelationId { get; set; } = string.Empty;
    public DateTimeOffset RequestedTime { get; set; }
    public DateTimeOffset? StartedTime { get; set; }
    public DateTimeOffset? CompletedTime { get; set; }
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
    public string OverlayObjectKey { get; set; } = string.Empty;
    public string ContourObjectKey { get; set; } = string.Empty;
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
