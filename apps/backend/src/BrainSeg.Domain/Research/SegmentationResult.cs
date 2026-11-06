using Volo.Abp;
using Volo.Abp.Domain.Entities.Auditing;

namespace BrainSeg.Research;

public class SegmentationResult : FullAuditedAggregateRoot<Guid>
{
    public Guid JobId { get; private set; }
    public string MaskObjectKey { get; private set; } = string.Empty;
    public string OverlayObjectKey { get; private set; } = string.Empty;
    public string ContourObjectKey { get; private set; } = string.Empty;
    public double? Dice { get; private set; }
    public double? IoU { get; private set; }
    public double? Precision { get; private set; }
    public double? Recall { get; private set; }
    public int TumorAreaPixels { get; private set; }
    public double TumorAreaRatio { get; private set; }
    public double InferenceMilliseconds { get; private set; }
    public double PreprocessingMilliseconds { get; private set; }
    public double PostprocessingMilliseconds { get; private set; }
    public DateTime CreatedTime { get; private set; }

    protected SegmentationResult() { }

    public SegmentationResult(Guid id, Guid jobId, string maskObjectKey, string overlayObjectKey,
        string contourObjectKey, int tumorAreaPixels, double inferenceMilliseconds,
        double preprocessingMilliseconds, double postprocessingMilliseconds, DateTime createdTime,
        double? dice = null, double? iou = null, double? precision = null, double? recall = null) : base(id)
    {
        ResearchGuard.Identifier(id, nameof(Id));
        JobId = ResearchGuard.Identifier(jobId, nameof(JobId));
        MaskObjectKey = ResearchGuard.ObjectKey(maskObjectKey, nameof(MaskObjectKey));
        OverlayObjectKey = ResearchGuard.ObjectKey(overlayObjectKey, nameof(OverlayObjectKey));
        ContourObjectKey = ResearchGuard.ObjectKey(contourObjectKey, nameof(ContourObjectKey));
        var metricCount = new[] { dice, iou, precision, recall }.Count(value => value.HasValue);
        if (metricCount is not (0 or 4) || tumorAreaPixels is < 0 or > 65536)
        {
            throw new BusinessException(ResearchErrors.InvalidMetrics);
        }
        Dice = ResearchGuard.Metric(dice);
        IoU = ResearchGuard.Metric(iou);
        Precision = ResearchGuard.Metric(precision);
        Recall = ResearchGuard.Metric(recall);
        TumorAreaPixels = tumorAreaPixels;
        TumorAreaRatio = tumorAreaPixels / 65536.0;
        InferenceMilliseconds = ResearchGuard.Nonnegative(inferenceMilliseconds, nameof(InferenceMilliseconds));
        PreprocessingMilliseconds = ResearchGuard.Nonnegative(preprocessingMilliseconds, nameof(PreprocessingMilliseconds));
        PostprocessingMilliseconds = ResearchGuard.Nonnegative(postprocessingMilliseconds, nameof(PostprocessingMilliseconds));
        CreatedTime = ResearchGuard.Utc(createdTime);
    }
}
