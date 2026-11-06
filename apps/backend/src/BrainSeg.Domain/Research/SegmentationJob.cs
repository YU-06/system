using Volo.Abp;
using Volo.Abp.Domain.Entities.Auditing;

namespace BrainSeg.Research;

public class SegmentationJob : FullAuditedAggregateRoot<Guid>
{
    public const int MaxRetries = 3;

    public Guid StudyId { get; private set; }
    public Guid ModelVersionId { get; private set; }
    public Guid RequesterId { get; private set; }
    public string IdempotencyKey { get; private set; } = string.Empty;
    public SegmentationJobStatus Status { get; private set; }
    public int Progress { get; private set; }
    public string CorrelationId { get; private set; } = string.Empty;
    public DateTime RequestedTime { get; private set; }
    public DateTime? StartedTime { get; private set; }
    public DateTime? CompletedTime { get; private set; }
    public string? ErrorCode { get; private set; }
    public string? ErrorMessage { get; private set; }
    public int RetryCount { get; private set; }

    protected SegmentationJob() { }

    public SegmentationJob(Guid id, Guid studyId, Guid modelVersionId, Guid requesterId,
        string idempotencyKey, string correlationId, DateTime requestedTime) : base(id)
    {
        ResearchGuard.Identifier(id, nameof(Id));
        StudyId = ResearchGuard.Identifier(studyId, nameof(StudyId));
        ModelVersionId = ResearchGuard.Identifier(modelVersionId, nameof(ModelVersionId));
        RequesterId = ResearchGuard.Identifier(requesterId, nameof(RequesterId));
        IdempotencyKey = ResearchGuard.Token(idempotencyKey, nameof(IdempotencyKey), 128);
        CorrelationId = ResearchGuard.Token(correlationId, nameof(CorrelationId));
        RequestedTime = ResearchGuard.Utc(requestedTime);
        Status = SegmentationJobStatus.Pending;
    }

    public void Start(DateTime now)
    {
        RequireStatus(SegmentationJobStatus.Pending);
        StartedTime = ResearchGuard.Utc(now, RequestedTime);
        Status = SegmentationJobStatus.Running;
    }

    public void ReportProgress(int progress)
    {
        RequireStatus(SegmentationJobStatus.Running);
        if (progress < Progress || progress is < 0 or >= 100)
        {
            throw new BusinessException(ResearchErrors.InvalidProgress);
        }
        Progress = progress;
    }

    public void Complete(DateTime now)
    {
        RequireStatus(SegmentationJobStatus.Running);
        CompletedTime = ResearchGuard.Utc(now, StartedTime);
        Progress = 100;
        Status = SegmentationJobStatus.Succeeded;
    }

    public void Fail(JobFailureReason reason, DateTime now)
    {
        RequireStatus(SegmentationJobStatus.Running);
        if (!Enum.IsDefined(reason))
        {
            throw new BusinessException(ResearchErrors.InvalidInput).WithData("Field", nameof(reason));
        }
        CompletedTime = ResearchGuard.Utc(now, StartedTime);
        (ErrorCode, ErrorMessage) = reason switch
        {
            JobFailureReason.InferenceTimeout => (ResearchErrors.InferenceTimeout, "Inference deadline exceeded."),
            JobFailureReason.ModelNotReady => (ResearchErrors.ModelNotReady, "A verified model is not ready."),
            JobFailureReason.InvalidInput => (ResearchErrors.InvalidInput, "Inference input validation failed."),
            _ => (ResearchErrors.ExecutionFailed, "Inference could not be completed.")
        };
        Status = SegmentationJobStatus.Failed;
    }

    public void Cancel(DateTime now)
    {
        if (Status is not (SegmentationJobStatus.Pending or SegmentationJobStatus.Running))
        {
            throw new BusinessException(ResearchErrors.IllegalJobTransition);
        }
        CompletedTime = ResearchGuard.Utc(now, StartedTime ?? RequestedTime);
        Status = SegmentationJobStatus.Cancelled;
    }

    public void Retry(DateTime now)
    {
        RequireStatus(SegmentationJobStatus.Failed);
        if (RetryCount >= MaxRetries)
        {
            throw new BusinessException(ResearchErrors.RetryLimitReached);
        }
        RequestedTime = ResearchGuard.Utc(now, CompletedTime);
        RetryCount++;
        Progress = 0;
        StartedTime = null;
        CompletedTime = null;
        ErrorCode = null;
        ErrorMessage = null;
        Status = SegmentationJobStatus.Pending;
    }

    private void RequireStatus(SegmentationJobStatus expected)
    {
        if (Status != expected)
        {
            throw new BusinessException(ResearchErrors.IllegalJobTransition)
                .WithData("Status", Status.ToString());
        }
    }
}
