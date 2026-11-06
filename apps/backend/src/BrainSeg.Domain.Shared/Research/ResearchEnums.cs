using System.Text.Json.Serialization;

namespace BrainSeg.Research;

[JsonConverter(typeof(JsonStringEnumConverter<BrainStudyStatus>))]
public enum BrainStudyStatus
{
    Uploaded,
    Ready,
    Archived
}

[JsonConverter(typeof(JsonStringEnumConverter<SegmentationJobStatus>))]
public enum SegmentationJobStatus
{
    Pending,
    Running,
    Succeeded,
    Failed,
    Cancelled
}

[JsonConverter(typeof(JsonStringEnumConverter<ModelArchitecture>))]
public enum ModelArchitecture
{
    UNet,
    AttentionUNet
}

[JsonConverter(typeof(JsonStringEnumConverter<JobFailureReason>))]
public enum JobFailureReason
{
    InferenceTimeout,
    ModelNotReady,
    InvalidInput,
    ExecutionFailed
}
