using Volo.Abp;
using Volo.Abp.Domain.Entities.Auditing;
using System.Text.Json;

namespace BrainSeg.Research;

public class SegmentationResult : FullAuditedAggregateRoot<Guid>
{
    public Guid JobId { get; private set; }
    public string MaskObjectKey { get; private set; } = string.Empty;
    public string? MaskSha256 { get; private set; }
    public string? OverlayObjectKey { get; private set; }
    public string? ContourObjectKey { get; private set; }
    public string? ProbabilityObjectKey { get; private set; }
    public string? ProbabilitySha256 { get; private set; }
    public string? BoundaryObjectKey { get; private set; }
    public string? BoundarySha256 { get; private set; }
    public string? UncertaintyObjectKey { get; private set; }
    public string? UncertaintySha256 { get; private set; }
    public string? ModelVarianceObjectKey { get; private set; }
    public string? ModelVarianceSha256 { get; private set; }
    public string InputMode { get; private set; } = "2d";
    public int ContextSlices { get; private set; } = 1;
    public string SliceFusion { get; private set; } = "stack";
    public bool BoundaryHead { get; private set; }
    public bool DeepSupervision { get; private set; }
    public string? MemberWeightHashesJson { get; private set; }
    public int EnsembleSize { get; private set; } = 1;
    public string? UncertaintyMethod { get; private set; }
    public double? MeanUncertainty { get; private set; }
    public double? P95Uncertainty { get; private set; }
    public string? CalibrationMetricsJson { get; private set; }
    public string? UncertaintyRetentionMetricsJson { get; private set; }
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
        string? remotePredictionSha256 = null, string? probabilityObjectKey = null,
        string? probabilitySha256 = null, string? boundaryObjectKey = null,
        string? boundarySha256 = null, string? uncertaintyObjectKey = null,
        string? uncertaintySha256 = null, string? modelVarianceObjectKey = null,
        string? modelVarianceSha256 = null, string inputMode = "2d", int contextSlices = 1,
        string sliceFusion = "stack", bool boundaryHead = false, bool deepSupervision = false,
        string? memberWeightHashesJson = null, int ensembleSize = 1,
        string? uncertaintyMethod = null, double? meanUncertainty = null,
        double? p95Uncertainty = null) : base(id)
    {
        ResearchGuard.Identifier(id, nameof(Id));
        JobId = ResearchGuard.Identifier(jobId, nameof(JobId));
        MaskObjectKey = ResearchGuard.ObjectKey(maskObjectKey, nameof(MaskObjectKey));
        MaskSha256 = ResearchGuard.Sha256(maskSha256, nameof(MaskSha256));
        OverlayObjectKey = overlayObjectKey is null ? null : ResearchGuard.ObjectKey(overlayObjectKey, nameof(OverlayObjectKey));
        ContourObjectKey = contourObjectKey is null ? null : ResearchGuard.ObjectKey(contourObjectKey, nameof(ContourObjectKey));
        ProbabilityObjectKey = ValidateArtifact(probabilityObjectKey, probabilitySha256, nameof(ProbabilityObjectKey));
        ProbabilitySha256 = probabilitySha256 is null ? null : ResearchGuard.Sha256(probabilitySha256, nameof(ProbabilitySha256));
        BoundaryObjectKey = ValidateArtifact(boundaryObjectKey, boundarySha256, nameof(BoundaryObjectKey));
        BoundarySha256 = boundarySha256 is null ? null : ResearchGuard.Sha256(boundarySha256, nameof(BoundarySha256));
        UncertaintyObjectKey = ValidateArtifact(uncertaintyObjectKey, uncertaintySha256, nameof(UncertaintyObjectKey));
        UncertaintySha256 = uncertaintySha256 is null ? null : ResearchGuard.Sha256(uncertaintySha256, nameof(UncertaintySha256));
        ModelVarianceObjectKey = ValidateArtifact(modelVarianceObjectKey, modelVarianceSha256, nameof(ModelVarianceObjectKey));
        ModelVarianceSha256 = modelVarianceSha256 is null ? null : ResearchGuard.Sha256(modelVarianceSha256, nameof(ModelVarianceSha256));
        if (inputMode is not ("2d" or "2p5d") || contextSlices is < 1 or > 9
            || contextSlices % 2 != 1 || sliceFusion is not ("stack" or "center_attention")
            || (inputMode == "2d" && (contextSlices != 1 || sliceFusion != "stack"))
            || ensembleSize < 1)
            throw new BusinessException(ResearchErrors.InvalidInput);
        InputMode = inputMode;
        ContextSlices = contextSlices;
        SliceFusion = sliceFusion;
        BoundaryHead = boundaryHead;
        DeepSupervision = deepSupervision;
        MemberWeightHashesJson = ValidateHashes(memberWeightHashesJson, ensembleSize);
        EnsembleSize = ensembleSize;
        UncertaintyMethod = uncertaintyMethod is null
            ? null : ResearchGuard.Text(uncertaintyMethod, nameof(UncertaintyMethod), 64);
        MeanUncertainty = ValidateUncertainty(meanUncertainty);
        P95Uncertainty = ValidateUncertainty(p95Uncertainty);
        if ((UncertaintyObjectKey is not null || ModelVarianceObjectKey is not null)
            && UncertaintyMethod is null)
            throw new BusinessException(ResearchErrors.InvalidInput);
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
        double dice, double iou, double precision, double recall,
        string? calibrationMetricsJson = null, string? uncertaintyRetentionMetricsJson = null)
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
        CalibrationMetricsJson = ValidateOptionalJson(calibrationMetricsJson);
        UncertaintyRetentionMetricsJson = ValidateOptionalJson(
            uncertaintyRetentionMetricsJson);
    }

    public void ClearEvaluation()
    {
        Dice = null;
        IoU = null;
        Precision = null;
        Recall = null;
        GroundTruthSha256 = null;
        EvaluationProtocol = null;
        CalibrationMetricsJson = null;
        UncertaintyRetentionMetricsJson = null;
    }

    private static string? ValidateArtifact(string? key, string? hash, string keyName)
    {
        if ((key is null) != (hash is null))
            throw new BusinessException(ResearchErrors.InvalidInput);
        return key is null ? null : ResearchGuard.ObjectKey(key, keyName);
    }

    private static string? ValidateHashes(string? json, int ensembleSize)
    {
        if (json is null)
        {
            if (ensembleSize != 1)
                throw new BusinessException(ResearchErrors.InvalidInput);
            return null;
        }
        try
        {
            using var document = JsonDocument.Parse(json);
            if (document.RootElement.ValueKind != JsonValueKind.Array
                || document.RootElement.GetArrayLength() != ensembleSize
                || document.RootElement.EnumerateArray().Any(value => !IsSha256(value)))
                throw new BusinessException(ResearchErrors.InvalidInput);
            return json;
        }
        catch (JsonException exception)
        {
            throw new BusinessException(ResearchErrors.InvalidInput).WithData("Cause", exception.GetType().Name);
        }
    }

    private static bool IsSha256(JsonElement value)
    {
        if (value.ValueKind != JsonValueKind.String) return false;
        var hash = value.GetString();
        return hash is { Length: 64 } && hash.All(Uri.IsHexDigit);
    }

    private static double? ValidateUncertainty(double? value)
    {
        if (value is null) return null;
        if (!double.IsFinite(value.Value) || value is < 0 or > 100)
            throw new BusinessException(ResearchErrors.InvalidMetrics);
        return value;
    }

    private static string? ValidateOptionalJson(string? value)
    {
        if (value is null) return null;
        if (value.Length > 16384)
            throw new BusinessException(ResearchErrors.InvalidInput);
        try
        {
            using var _ = JsonDocument.Parse(value);
            return value;
        }
        catch (JsonException exception)
        {
            throw new BusinessException(ResearchErrors.InvalidInput).WithData("Cause", exception.GetType().Name);
        }
    }
}
