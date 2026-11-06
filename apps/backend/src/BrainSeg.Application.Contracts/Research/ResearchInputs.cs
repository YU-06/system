using System.ComponentModel.DataAnnotations;
using Volo.Abp.Application.Dtos;
using Volo.Abp.Auditing;
using Volo.Abp.Content;

namespace BrainSeg.Research;

public class ResearchListInput : PagedAndSortedResultRequestDto
{
    [StringLength(128)]
    public string? Filter { get; set; }
}

public sealed class BrainStudyListInput : ResearchListInput
{
    public BrainStudyStatus? Status { get; set; }
}

public sealed class SegmentationJobListInput : ResearchListInput
{
    public Guid? StudyId { get; set; }
    public Guid? ModelVersionId { get; set; }
    public SegmentationJobStatus? Status { get; set; }
}

public sealed class ModelVersionListInput : ResearchListInput
{
    public ModelArchitecture? Architecture { get; set; }
    public bool? IsActive { get; set; }
}

public sealed class SegmentationResultListInput : ResearchListInput
{
    public Guid? JobId { get; set; }
}

public sealed class ExperimentRunListInput : ResearchListInput
{
    public Guid? ModelVersionId { get; set; }
    public int? RandomSeed { get; set; }
}

public sealed class UploadBrainStudyInput
{
    [Required, StringLength(64)]
    public string StudyNumber { get; set; } = string.Empty;
    [Required, StringLength(64)]
    public string Pseudonym { get; set; } = string.Empty;
    [Range(0, 511)]
    public int SliceIndex { get; set; }
    [Required, DisableAuditing]
    public IRemoteStreamContent File { get; set; } = null!;
}

public class ResearchCommandInput
{
    [Required, StringLength(40, MinimumLength = 1)]
    public string ConcurrencyStamp { get; set; } = string.Empty;
}

public sealed class UpdateBrainStudyInput : ResearchCommandInput
{
    [Required, StringLength(64)]
    public string Pseudonym { get; set; } = string.Empty;
}

public sealed class CreateSegmentationJobInput
{
    public Guid StudyId { get; set; }
    public Guid ModelVersionId { get; set; }
    [Required, StringLength(128)]
    public string IdempotencyKey { get; set; } = string.Empty;
}

public sealed class ReportJobProgressInput : ResearchCommandInput
{
    [Range(0, 99)]
    public int Progress { get; set; }
}

public sealed class FailSegmentationJobInput : ResearchCommandInput
{
    public JobFailureReason Reason { get; set; }
}

public sealed class CompleteSegmentationJobInput : ResearchCommandInput
{
    [Required, StringLength(512)]
    public string MaskObjectKey { get; set; } = string.Empty;
    [Required, StringLength(512)]
    public string OverlayObjectKey { get; set; } = string.Empty;
    [Required, StringLength(512)]
    public string ContourObjectKey { get; set; } = string.Empty;
    [Range(0, 65536)]
    public int TumorAreaPixels { get; set; }
    public double InferenceMilliseconds { get; set; }
    public double PreprocessingMilliseconds { get; set; }
    public double PostprocessingMilliseconds { get; set; }
    public double? Dice { get; set; }
    public double? IoU { get; set; }
    public double? Precision { get; set; }
    public double? Recall { get; set; }
}

public sealed class CreateModelVersionInput
{
    [Required, StringLength(128)]
    public string Name { get; set; } = string.Empty;
    public ModelArchitecture Architecture { get; set; }
    [Required, StringLength(64)]
    public string SemanticVersion { get; set; } = string.Empty;
    [Required, StringLength(512)]
    public string WeightObjectKey { get; set; } = string.Empty;
    [Required, StringLength(64, MinimumLength = 64)]
    public string WeightSha256 { get; set; } = string.Empty;
    [Range(0.000001, 0.999999)]
    public double Threshold { get; set; } = 0.5;
    [Required, StringLength(16384)]
    public string MetricsJson { get; set; } = "{\"status\":\"NotRun\"}";
}

public sealed class ChangeModelStateInput : ResearchCommandInput
{
    public bool IsActive { get; set; }
    public bool IsDefault { get; set; }
}

public sealed class CreateExperimentRunInput
{
    [Required, StringLength(128)]
    public string ExperimentName { get; set; } = string.Empty;
    [Required, StringLength(64, MinimumLength = 64)]
    public string ConfigHash { get; set; } = string.Empty;
    [Required, StringLength(64, MinimumLength = 40)]
    public string GitCommit { get; set; } = string.Empty;
    [Required, StringLength(64, MinimumLength = 64)]
    public string DatasetSplitHash { get; set; } = string.Empty;
    [Range(0, int.MaxValue)]
    public int RandomSeed { get; set; }
    public Guid ModelVersionId { get; set; }
    [Required, StringLength(16384)]
    public string MetricsJson { get; set; } = "{\"status\":\"NotRun\"}";
    [Required, StringLength(512)]
    public string ArtifactObjectKey { get; set; } = string.Empty;
}
