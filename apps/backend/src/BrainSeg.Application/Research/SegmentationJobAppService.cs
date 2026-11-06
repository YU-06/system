using System.Linq.Expressions;
using Microsoft.AspNetCore.Authorization;
using Volo.Abp;
using Volo.Abp.Application.Dtos;
using Volo.Abp.Authorization;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Tracing;
using Volo.Abp.Uow;
using Volo.Abp.Users;

namespace BrainSeg.Research;

[Authorize(ResearchPermissions.SegmentationJobs.Default)]
public class SegmentationJobAppService(ISegmentationJobRepository jobs, IBrainStudyRepository studies,
    IModelVersionRepository models, ISegmentationResultRepository results, ResearchArtifactService artifacts,
    ICorrelationIdProvider correlationIdProvider) : ResearchAppService, ISegmentationJobAppService
{
    private static readonly IReadOnlyDictionary<string, Expression<Func<SegmentationJob, object>>> Sorting =
        new Dictionary<string, Expression<Func<SegmentationJob, object>>>(StringComparer.OrdinalIgnoreCase)
        {
            ["creationTime"] = value => value.CreationTime,
            ["requestedTime"] = value => value.RequestedTime,
            ["status"] = value => value.Status,
            ["progress"] = value => value.Progress
        };

    public virtual async Task<SegmentationJobDto> GetAsync(Guid id, CancellationToken cancellationToken = default) =>
        Map<SegmentationJob, SegmentationJobDto>(await jobs.GetAsync(id, cancellationToken: cancellationToken));

    public virtual async Task<PagedResultDto<SegmentationJobDto>> GetListAsync(SegmentationJobListInput input, CancellationToken cancellationToken = default)
    {
        var query = await jobs.GetQueryableAsync();
        if (input.StudyId.HasValue) query = query.Where(value => value.StudyId == input.StudyId);
        if (input.ModelVersionId.HasValue) query = query.Where(value => value.ModelVersionId == input.ModelVersionId);
        if (input.Status.HasValue) query = query.Where(value => value.Status == input.Status);
        if (!string.IsNullOrWhiteSpace(input.Filter))
        {
            var filter = input.Filter.Trim().ToLowerInvariant();
            query = query.Where(value => value.CorrelationId.ToLower().Contains(filter) || value.IdempotencyKey.ToLower().Contains(filter));
        }
        return await PageAsync<SegmentationJob, SegmentationJobDto>(query, input, Sorting, cancellationToken);
    }

    [Authorize(ResearchPermissions.SegmentationJobs.Create)]
    [UnitOfWork(isTransactional: true)]
    public virtual async Task<SegmentationJobDto> CreateAsync(CreateSegmentationJobInput input, CancellationToken cancellationToken = default)
    {
        var requester = CurrentUser.Id ?? throw new AbpAuthorizationException("A user identity is required to request a job.");
        var correlation = correlationIdProvider.Get();
        if (string.IsNullOrEmpty(correlation)) correlation = GuidGenerator.Create().ToString("N");
        var candidate = new SegmentationJob(GuidGenerator.Create(), input.StudyId, input.ModelVersionId,
            requester, input.IdempotencyKey, correlation, Clock.Now);
        var existing = await jobs.FindAsync(value => value.RequesterId == requester && value.IdempotencyKey == candidate.IdempotencyKey,
            cancellationToken: cancellationToken);
        if (existing is not null)
        {
            if (existing.StudyId != input.StudyId || existing.ModelVersionId != input.ModelVersionId)
                throw new BusinessException(ResearchErrors.IdempotencyConflict);
            return Map<SegmentationJob, SegmentationJobDto>(existing);
        }
        var study = await studies.GetAsync(input.StudyId, cancellationToken: cancellationToken);
        (await models.GetAsync(input.ModelVersionId, cancellationToken: cancellationToken)).EnsureActive();
        study.RecordJobRequest();
        await studies.UpdateAsync(study, autoSave: true, cancellationToken: cancellationToken);
        await jobs.InsertAsync(candidate, autoSave: true, cancellationToken: cancellationToken);
        return Map<SegmentationJob, SegmentationJobDto>(candidate);
    }

    [Authorize(ResearchPermissions.SegmentationJobs.Execute)]
    public virtual async Task<SegmentationJobDto> StartAsync(Guid id, ResearchCommandInput input, CancellationToken cancellationToken = default)
    {
        var job = await CommandAsync(id, input, cancellationToken);
        job.Start(Clock.Now);
        return await SaveAsync(job, cancellationToken);
    }

    [Authorize(ResearchPermissions.SegmentationJobs.Execute)]
    public virtual async Task<SegmentationJobDto> ReportProgressAsync(Guid id, ReportJobProgressInput input, CancellationToken cancellationToken = default)
    {
        var job = await CommandAsync(id, input, cancellationToken);
        job.ReportProgress(input.Progress);
        return await SaveAsync(job, cancellationToken);
    }

    [Authorize(ResearchPermissions.SegmentationJobs.Execute)]
    public virtual async Task<SegmentationJobDto> FailAsync(Guid id, FailSegmentationJobInput input, CancellationToken cancellationToken = default)
    {
        var job = await CommandAsync(id, input, cancellationToken);
        job.Fail(input.Reason, Clock.Now);
        return await SaveAsync(job, cancellationToken);
    }

    [Authorize(ResearchPermissions.SegmentationJobs.Cancel)]
    public virtual async Task<SegmentationJobDto> CancelAsync(Guid id, ResearchCommandInput input, CancellationToken cancellationToken = default)
    {
        var job = await CommandAsync(id, input, cancellationToken);
        job.Cancel(Clock.Now);
        return await SaveAsync(job, cancellationToken);
    }

    [Authorize(ResearchPermissions.SegmentationJobs.Retry)]
    [UnitOfWork(isTransactional: true)]
    public virtual async Task<SegmentationJobDto> RetryAsync(Guid id, ResearchCommandInput input, CancellationToken cancellationToken = default)
    {
        var job = await CommandAsync(id, input, cancellationToken);
        (await models.GetAsync(job.ModelVersionId, cancellationToken: cancellationToken)).EnsureActive();
        var study = await studies.GetAsync(job.StudyId, cancellationToken: cancellationToken);
        job.Retry(Clock.Now);
        study.RecordJobRequest();
        await studies.UpdateAsync(study, autoSave: true, cancellationToken: cancellationToken);
        return await SaveAsync(job, cancellationToken);
    }

    [Authorize(ResearchPermissions.SegmentationJobs.Execute)]
    [UnitOfWork(isTransactional: true)]
    public virtual async Task<SegmentationResultDto> CompleteAsync(Guid id, CompleteSegmentationJobInput input, CancellationToken cancellationToken = default)
    {
        var job = await CommandAsync(id, input, cancellationToken);
        var result = new SegmentationResult(GuidGenerator.Create(), id, input.MaskObjectKey, input.OverlayObjectKey,
            input.ContourObjectKey, input.TumorAreaPixels, input.InferenceMilliseconds, input.PreprocessingMilliseconds,
            input.PostprocessingMilliseconds, Clock.Now, input.Dice, input.IoU, input.Precision, input.Recall);
        job.Complete(Clock.Now);
        await artifacts.VerifyAsync(result.MaskObjectKey, null, cancellationToken);
        await artifacts.VerifyAsync(result.OverlayObjectKey, null, cancellationToken);
        await artifacts.VerifyAsync(result.ContourObjectKey, null, cancellationToken);
        await results.InsertAsync(result, autoSave: true, cancellationToken: cancellationToken);
        await jobs.UpdateAsync(job, autoSave: true, cancellationToken: cancellationToken);
        return Map<SegmentationResult, SegmentationResultDto>(result);
    }

    private async Task<SegmentationJob> CommandAsync(Guid id, ResearchCommandInput input, CancellationToken cancellationToken)
    {
        var job = await jobs.GetAsync(id, cancellationToken: cancellationToken);
        CheckStamp(job.ConcurrencyStamp, input.ConcurrencyStamp);
        return job;
    }

    private async Task<SegmentationJobDto> SaveAsync(SegmentationJob job, CancellationToken cancellationToken)
    {
        await jobs.UpdateAsync(job, autoSave: true, cancellationToken: cancellationToken);
        return Map<SegmentationJob, SegmentationJobDto>(job);
    }
}
