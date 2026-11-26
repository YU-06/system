namespace BrainSeg.Inference;

public sealed class InferenceClientException(string code, bool retryable,
    global::System.Net.HttpStatusCode? statusCode = null) : Exception(code)
{
    public string Code { get; } = code;
    public bool Retryable { get; } = retryable;
    public global::System.Net.HttpStatusCode? StatusCode { get; } = statusCode;
}

public sealed record InferenceTimings(double PreprocessingMilliseconds, double InferenceMilliseconds,
    double PostprocessingMilliseconds);

public sealed record InferenceSegmentResponse(
    string ModelVersion,
    string Architecture,
    string ArtifactKind,
    string PreprocessingVersion,
    int InputSize,
    double Threshold,
    string CorrelationId,
    string RequestId,
    string InputSha256,
    string? WeightSha256,
    string? ModelManifestSha256,
    string PredictionObjectKey,
    string PredictionSha256,
    int[] MaskShape,
    string Space,
    int TumorAreaPixels,
    double TumorAreaRatio,
    InferenceTimings Timings);

public sealed record InferenceMetrics(double Dice, double Iou, double Precision, double Recall);

public sealed record InferenceEvaluationResponse(
    string ModelVersion,
    string Architecture,
    string ArtifactKind,
    string PreprocessingVersion,
    string EvaluationProtocol,
    double Threshold,
    string? WeightSha256,
    string? ModelManifestSha256,
    string RequestId,
    string CorrelationId,
    string InputSha256,
    string GroundTruthSha256,
    string PredictionObjectKey,
    string PredictionSha256,
    InferenceMetrics PatientMetrics,
    InferenceMetrics SliceMacroMetrics,
    int SliceCount);

public sealed class InferencePredictionDownload(HttpResponseMessage response, Stream content, string sha256)
    : IAsyncDisposable
{
    public Stream Content { get; } = content;
    public string Sha256 { get; } = sha256;

    public async ValueTask DisposeAsync()
    {
        await Content.DisposeAsync();
        response.Dispose();
    }
}

public interface IMlInferenceClient
{
    Task<InferenceSegmentResponse> SegmentAsync(string inputObjectKey, string expectedInputSha256,
        string requestId, string correlationId, CancellationToken cancellationToken);

    Task<InferencePredictionDownload> OpenPredictionAsync(string predictionObjectKey, string correlationId,
        CancellationToken cancellationToken);

    Task<InferenceEvaluationResponse> EvaluateAsync(string inputObjectKey, string groundTruthObjectKey,
        string predictionObjectKey, string correlationId, CancellationToken cancellationToken);
}
