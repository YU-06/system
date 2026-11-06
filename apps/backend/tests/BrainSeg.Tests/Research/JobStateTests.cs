using BrainSeg.Research;
using Volo.Abp;
using Xunit;

namespace BrainSeg.Tests.Research;

public class JobStateTests
{
    private static readonly DateTime Requested = new(2026, 11, 6, 0, 0, 0, DateTimeKind.Utc);

    internal static SegmentationJob CreateJob() => new(Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid(),
        Guid.NewGuid(), "request-001", "correlation-001", Requested);

    [Fact]
    public void Successful_job_has_monotonic_progress_and_utc_timestamps()
    {
        var job = CreateJob();
        Assert.Equal(SegmentationJobStatus.Pending, job.Status);
        job.Start(Requested.AddSeconds(1));
        job.ReportProgress(50);
        Assert.Equal(ResearchErrors.InvalidProgress,
            Assert.Throws<BusinessException>(() => job.ReportProgress(49)).Code);
        Assert.Throws<BusinessException>(() => job.ReportProgress(100));
        job.Complete(Requested.AddSeconds(2));
        Assert.Equal(SegmentationJobStatus.Succeeded, job.Status);
        Assert.Equal(100, job.Progress);
        Assert.Equal(DateTimeKind.Utc, job.CompletedTime!.Value.Kind);
    }

    [Theory]
    [InlineData(SegmentationJobStatus.Pending, "complete")]
    [InlineData(SegmentationJobStatus.Pending, "fail")]
    [InlineData(SegmentationJobStatus.Pending, "retry")]
    [InlineData(SegmentationJobStatus.Pending, "progress")]
    [InlineData(SegmentationJobStatus.Running, "start")]
    [InlineData(SegmentationJobStatus.Running, "retry")]
    [InlineData(SegmentationJobStatus.Succeeded, "start")]
    [InlineData(SegmentationJobStatus.Succeeded, "complete")]
    [InlineData(SegmentationJobStatus.Succeeded, "fail")]
    [InlineData(SegmentationJobStatus.Succeeded, "retry")]
    [InlineData(SegmentationJobStatus.Succeeded, "cancel")]
    [InlineData(SegmentationJobStatus.Succeeded, "progress")]
    [InlineData(SegmentationJobStatus.Failed, "start")]
    [InlineData(SegmentationJobStatus.Failed, "complete")]
    [InlineData(SegmentationJobStatus.Failed, "cancel")]
    [InlineData(SegmentationJobStatus.Failed, "fail")]
    [InlineData(SegmentationJobStatus.Failed, "progress")]
    [InlineData(SegmentationJobStatus.Cancelled, "start")]
    [InlineData(SegmentationJobStatus.Cancelled, "complete")]
    [InlineData(SegmentationJobStatus.Cancelled, "fail")]
    [InlineData(SegmentationJobStatus.Cancelled, "retry")]
    [InlineData(SegmentationJobStatus.Cancelled, "cancel")]
    [InlineData(SegmentationJobStatus.Cancelled, "progress")]
    public void Illegal_transitions_are_rejected(SegmentationJobStatus status, string command)
    {
        var job = CreateJob();
        if (status != SegmentationJobStatus.Pending)
        {
            job.Start(Requested);
        }
        switch (status)
        {
            case SegmentationJobStatus.Succeeded: job.Complete(Requested); break;
            case SegmentationJobStatus.Failed: job.Fail(JobFailureReason.ExecutionFailed, Requested); break;
            case SegmentationJobStatus.Cancelled: job.Cancel(Requested); break;
        }
        Action action = command switch
        {
            "start" => () => job.Start(Requested),
            "complete" => () => job.Complete(Requested),
            "fail" => () => job.Fail(JobFailureReason.ExecutionFailed, Requested),
            "retry" => () => job.Retry(Requested),
            "progress" => () => job.ReportProgress(1),
            _ => () => job.Cancel(Requested)
        };
        Assert.Equal(ResearchErrors.IllegalJobTransition, Assert.Throws<BusinessException>(action).Code);
    }

    [Fact]
    public void Failed_job_can_retry_only_three_times_and_clears_previous_attempt()
    {
        var job = CreateJob();
        for (var attempt = 0; attempt < SegmentationJob.MaxRetries; attempt++)
        {
            job.Start(Requested);
            job.ReportProgress(80);
            job.Fail(JobFailureReason.InferenceTimeout, Requested);
            job.Retry(Requested);
            Assert.Equal(attempt + 1, job.RetryCount);
            Assert.Equal(SegmentationJobStatus.Pending, job.Status);
            Assert.Equal(0, job.Progress);
            Assert.Null(job.StartedTime);
            Assert.Null(job.CompletedTime);
            Assert.Null(job.ErrorCode);
            Assert.Null(job.ErrorMessage);
        }
        job.Start(Requested);
        job.Fail(JobFailureReason.ModelNotReady, Requested);
        Assert.Equal(ResearchErrors.RetryLimitReached,
            Assert.Throws<BusinessException>(() => job.Retry(Requested)).Code);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Pending_and_running_jobs_can_be_cancelled(bool running)
    {
        var job = CreateJob();
        if (running) job.Start(Requested);
        job.Cancel(Requested);
        Assert.Equal(SegmentationJobStatus.Cancelled, job.Status);
        Assert.NotNull(job.CompletedTime);
    }

    [Fact]
    public void Invalid_time_or_correlation_id_cannot_enter_the_aggregate()
    {
        var job = CreateJob();
        Assert.Equal(ResearchErrors.InvalidTimestamp,
            Assert.Throws<BusinessException>(() => job.Start(Requested.AddSeconds(-1))).Code);
        Assert.Throws<BusinessException>(() => job.Start(DateTime.SpecifyKind(Requested, DateTimeKind.Unspecified)));
        Assert.Throws<BusinessException>(() => new SegmentationJob(Guid.NewGuid(), Guid.NewGuid(),
            Guid.NewGuid(), Guid.NewGuid(), "key", "unsafe id", Requested));
    }
}
