using Volo.Abp;
using Volo.Abp.Domain.Entities.Auditing;

namespace BrainSeg.Research;

public class SegmentationResult : FullAuditedAggregateRoot<Guid>
{
    public Guid JobId { get; private set; }
    public string MaskObjectKey { get; private set; } = string.Empty;
    public string? MaskSha256 { get; private set; }
    public string? OverlayObjectKey { get; private set; }
    public string? ContourObjectKey { get; private set; }
    public string? RemotePredictionObjectKey { get; private set; }
    public string? RemotePredictionSha256 { get; private set; }
    public string? GroundTruthSha256 { get; private set; }
    public string? EvaluationProtocol { get; private set; }
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

    public SegmentationResult(Guid id, Guid jobId, string maskObjectKey, string maskSha256,
        string? overlayObjectKey, string? contourObjectKey, int tumorAreaPixels, double tumorAreaRatio,
        double inferenceMilliseconds, double preprocessingMilliseconds, double postprocessingMilliseconds,
        DateTime createdTime, double? dice = null, double? iou = null, double? precision = null,
        double? recall = null, string? remotePredictionObjectKey = null,
        string? remotePredictionSha256 = null) : base(id)
    {
        ResearchGuard.Identifier(id, nameof(Id));
        JobId = ResearchGuard.Identifier(jobId, nameof(JobId));
        MaskObjectKey = ResearchGuard.ObjectKey(maskObjectKey, nameof(MaskObjectKey));
        MaskSha256 = ResearchGuard.Sha256(maskSha256, nameof(MaskSha256));
        OverlayObjectKey = overlayObjectKey is null ? null : ResearchGuard.ObjectKey(overlayObjectKey, nameof(OverlayObjectKey));
        ContourObjectKey = contourObjectKey is null ? null : ResearchGuard.ObjectKey(contourObjectKey, nameof(ContourObjectKey));
        RemotePredictionObjectKey = remotePredictionObjectKey is null
            ? null : ResearchGuard.ObjectKey(remotePredictionObjectKey, nameof(RemotePredictionObjectKey));
        RemotePredictionSha256 = remotePredictionSha256 is null
            ? null : ResearchGuard.Sha256(remotePredictionSha256, nameof(RemotePredictionSha256));
        var metricCount = new[] { dice, iou, precision, recall }.Count(value => value.HasValue);
        if (metricCount is not (0 or 4) || tumorAreaPixels is < 0 or > 65536
            || !double.IsFinite(tumorAreaRatio) || tumorAreaRatio is < 0 or > 1)
        {
            throw new BusinessException(ResearchErrors.InvalidMetrics);
        }
        Dice = ResearchGuard.Metric(dice);
        IoU = ResearchGuard.Metric(iou);
        Precision = ResearchGuard.Metric(precision);
        Recall = ResearchGuard.Metric(recall);
        TumorAreaPixels = tumorAreaPixels;
        TumorAreaRatio = tumorAreaRatio;
        InferenceMilliseconds = ResearchGuard.Nonnegative(inferenceMilliseconds, nameof(InferenceMilliseconds));
        PreprocessingMilliseconds = ResearchGuard.Nonnegative(preprocessingMilliseconds, nameof(PreprocessingMilliseconds));
        PostprocessingMilliseconds = ResearchGuard.Nonnegative(postprocessingMilliseconds, nameof(PostprocessingMilliseconds));
        CreatedTime = ResearchGuard.Utc(createdTime);
    }

    public void RecordEvaluation(string groundTruthSha256, string protocol,
        double dice, double iou, double precision, double recall)
    {
        if (RemotePredictionObjectKey is null || RemotePredictionSha256 is null
            || protocol != "whole-tumor-v1")
            throw new BusinessException(ResearchErrors.InvalidInput);
        GroundTruthSha256 = ResearchGuard.Sha256(groundTruthSha256, nameof(groundTruthSha256));
        Dice = ResearchGuard.Metric(dice);
        IoU = ResearchGuard.Metric(iou);
        Precision = ResearchGuard.Metric(precision);
        Recall = ResearchGuard.Metric(recall);
        EvaluationProtocol = protocol;
    }

    public void ClearEvaluation()
    {
        Dice = null;
        IoU = null;
        Precision = null;
        Recall = null;
        GroundTruthSha256 = null;
        EvaluationProtocol = null;
    }
}
