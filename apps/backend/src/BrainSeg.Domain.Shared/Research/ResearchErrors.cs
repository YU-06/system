namespace BrainSeg.Research;

public static class ResearchErrors
{
    public const string InvalidInput = "BrainSeg:InvalidInput";
    public const string InvalidTimestamp = "BrainSeg:InvalidTimestamp";
    public const string IllegalJobTransition = "BrainSeg:IllegalJobTransition";
    public const string InvalidProgress = "BrainSeg:InvalidProgress";
    public const string RetryLimitReached = "BrainSeg:RetryLimitReached";
    public const string InferenceTimeout = "BrainSeg:InferenceTimeout";
    public const string ModelNotReady = "BrainSeg:ModelNotReady";
    public const string ExecutionFailed = "BrainSeg:ExecutionFailed";
    public const string IllegalStudyTransition = "BrainSeg:IllegalStudyTransition";
    public const string StudyNotReady = "BrainSeg:StudyNotReady";
    public const string StudyHasActiveJobs = "BrainSeg:StudyHasActiveJobs";
    public const string DuplicateStudy = "BrainSeg:DuplicateStudy";
    public const string DuplicateModelVersion = "BrainSeg:DuplicateModelVersion";
    public const string IdempotencyConflict = "BrainSeg:IdempotencyConflict";
    public const string InvalidSorting = "BrainSeg:InvalidSorting";
    public const string InvalidFile = "BrainSeg:InvalidFile";
    public const string UploadTooLarge = "BrainSeg:UploadTooLarge";
    public const string ArtifactUnavailable = "BrainSeg:ArtifactUnavailable";
    public const string ArtifactHashMismatch = "BrainSeg:ArtifactHashMismatch";
    public const string InvalidMetrics = "BrainSeg:InvalidMetrics";
    public const string DefaultModelConflict = "BrainSeg:DefaultModelConflict";
    public const string ResultAlreadyExists = "BrainSeg:ResultAlreadyExists";
    public const string DuplicateExperiment = "BrainSeg:DuplicateExperiment";
}
