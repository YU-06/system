using System.Linq.Expressions;
using BrainSeg.Storage;
using Microsoft.AspNetCore.Authorization;
using Microsoft.Extensions.Logging;
using Volo.Abp;
using Volo.Abp.Application.Dtos;
using Volo.Abp.Content;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Uow;

namespace BrainSeg.Research;

[Authorize(ResearchPermissions.BrainStudies.Default)]
public class BrainStudyAppService(IBrainStudyRepository studies, ISegmentationJobRepository jobs,
    ISegmentationResultRepository results,
    IObjectStorage storage, ResearchArtifactService artifacts, IObjectWriteIntentManager intents,
    ILogger<BrainStudyAppService> logger)
    : ResearchAppService, IBrainStudyAppService
{
    private static readonly IReadOnlyDictionary<string, Expression<Func<BrainStudy, object>>> Sorting =
        new Dictionary<string, Expression<Func<BrainStudy, object>>>(StringComparer.OrdinalIgnoreCase)
        {
            ["creationTime"] = value => value.CreationTime,
            ["studyNumber"] = value => value.StudyNumber,
            ["pseudonym"] = value => value.Pseudonym,
            ["status"] = value => value.Status
        };

    public virtual async Task<BrainStudyDto> GetAsync(Guid id, CancellationToken cancellationToken = default) =>
        Map<BrainStudy, BrainStudyDto>(await studies.GetAsync(id, cancellationToken: cancellationToken));

    public virtual async Task<PagedResultDto<BrainStudyDto>> GetListAsync(BrainStudyListInput input, CancellationToken cancellationToken = default)
    {
        var query = await studies.GetQueryableAsync();
        if (!string.IsNullOrWhiteSpace(input.Filter))
        {
            var filter = input.Filter.Trim().ToLowerInvariant();
            query = query.Where(value => value.StudyNumber.ToLower().Contains(filter) || value.Pseudonym.ToLower().Contains(filter));
        }
        if (input.Status.HasValue) query = query.Where(value => value.Status == input.Status);
        return await PageAsync<BrainStudy, BrainStudyDto>(query, input, Sorting, cancellationToken);
    }

    [Authorize(ResearchPermissions.BrainStudies.Create)]
    public virtual async Task<BrainStudyDto> UploadAsync(UploadBrainStudyInput input, CancellationToken cancellationToken = default)
    {
        var objectKey = $"{GuidGenerator.Create():N}.bin";
        await intents.RegisterAsync(objectKey, "study-upload", cancellationToken);
        await using var content = input.File.GetStream();
        var saved = await storage.SaveAsync(objectKey, content, cancellationToken);
        try
        {
            var file = await artifacts.ValidateStoredStudyAsync(saved.ObjectKey, input.File.FileName,
                input.File.ContentType, saved.Sha256, input.SliceIndex, cancellationToken);
            if (await studies.AnyAsync(value => value.StudyNumber == input.StudyNumber.Trim().ToUpperInvariant()
                || value.OriginalFileSha256 == file.Sha256 && value.SliceIndex == input.SliceIndex,
                cancellationToken))
                throw new BusinessException(ResearchErrors.DuplicateStudy);
            var study = new BrainStudy(GuidGenerator.Create(), input.StudyNumber, input.Pseudonym,
                saved.ObjectKey, file.Sha256, file.Width, file.Height, input.SliceIndex);
            study.MarkReady();
            await studies.InsertAsync(study, autoSave: true, cancellationToken: cancellationToken);
            await intents.CompleteInCurrentUnitOfWorkAsync(saved.ObjectKey, cancellationToken);
            return Map<BrainStudy, BrainStudyDto>(study);
        }
        catch
        {
            try
            {
                await storage.DeleteAsync(saved.ObjectKey, CancellationToken.None);
            }
            catch (Exception exception)
            {
                logger.LogError(exception, "Study upload cleanup deferred for object {ObjectKey}", saved.ObjectKey);
            }
            throw;
        }
    }

    [Authorize(ResearchPermissions.BrainStudies.RegisterGroundTruth)]
    [UnitOfWork(isTransactional: true)]
    public virtual async Task<BrainStudyDto> RegisterGroundTruthAsync(Guid id, UploadGroundTruthInput input,
        CancellationToken cancellationToken = default)
    {
        var study = await studies.GetAsync(id, cancellationToken: cancellationToken);
        study.EnsureReady();
        var objectKey = $"{GuidGenerator.Create():N}.bin";
        await intents.RegisterAsync(objectKey, "ground-truth-upload", cancellationToken);
        await using var content = input.File.GetStream();
        var saved = await storage.SaveAsync(objectKey, content, cancellationToken);
        try
        {
            var file = await artifacts.ValidateStoredStudyAsync(saved.ObjectKey, input.File.FileName,
                input.File.ContentType, saved.Sha256, study.SliceIndex, cancellationToken);
            if (file.Width != study.Width || file.Height != study.Height)
                throw new BusinessException(ResearchErrors.InvalidFile);
            study.RegisterGroundTruth(saved.ObjectKey, saved.Sha256);
            await studies.UpdateAsync(study, autoSave: true, cancellationToken: cancellationToken);
            await intents.CompleteInCurrentUnitOfWorkAsync(saved.ObjectKey, cancellationToken);
            return Map<BrainStudy, BrainStudyDto>(study);
        }
        catch
        {
            try
            {
                await storage.DeleteAsync(saved.ObjectKey, CancellationToken.None);
            }
            catch (Exception exception)
            {
                logger.LogError(exception, "Ground-truth cleanup deferred for object {ObjectKey}", saved.ObjectKey);
            }
            throw;
        }
    }

    [Authorize(ResearchPermissions.SegmentationResults.Download)]
    public virtual async Task<IRemoteStreamContent> DownloadGroundTruthAsync(Guid id,
        CancellationToken cancellationToken = default)
    {
        var study = await studies.GetAsync(id, cancellationToken: cancellationToken);
        if (study.GroundTruthObjectKey is null)
            throw new BusinessException(ResearchErrors.GroundTruthNotRegistered);
        await artifacts.VerifyAsync(study.GroundTruthObjectKey, study.GroundTruthSha256, cancellationToken);
        var stream = await storage.OpenReadAsync(study.GroundTruthObjectKey, cancellationToken);
        return new RemoteStreamContent(stream, "ground-truth.bin", "application/octet-stream");
    }

    [Authorize(ResearchPermissions.BrainStudies.DeleteGroundTruth)]
    [UnitOfWork(isTransactional: true)]
    public virtual async Task DeleteGroundTruthAsync(Guid id, ResearchCommandInput input,
        CancellationToken cancellationToken = default)
    {
        var study = await studies.GetAsync(id, cancellationToken: cancellationToken);
        CheckStamp(study.ConcurrencyStamp, input.ConcurrencyStamp);
        var objectKey = study.GroundTruthObjectKey
            ?? throw new BusinessException(ResearchErrors.GroundTruthNotRegistered);
        await intents.RegisterAsync(objectKey, "ground-truth-delete", cancellationToken);
        study.RemoveGroundTruth();
        await studies.UpdateAsync(study, autoSave: true, cancellationToken: cancellationToken);

        var jobIds = (await jobs.GetQueryableAsync()).Where(job => job.StudyId == id).Select(job => job.Id);
        var relatedResults = await AsyncExecuter.ToListAsync(
            (await results.GetQueryableAsync()).Where(result => jobIds.Contains(result.JobId)),
            cancellationToken);
        foreach (var result in relatedResults)
        {
            result.ClearEvaluation();
            await results.UpdateAsync(result, autoSave: true, cancellationToken: cancellationToken);
        }
    }

    [Authorize(ResearchPermissions.BrainStudies.Update)]
    public virtual async Task<BrainStudyDto> UpdateAsync(Guid id, UpdateBrainStudyInput input, CancellationToken cancellationToken = default)
    {
        var study = await studies.GetAsync(id, cancellationToken: cancellationToken);
        CheckStamp(study.ConcurrencyStamp, input.ConcurrencyStamp);
        study.ChangePseudonym(input.Pseudonym);
        await studies.UpdateAsync(study, autoSave: true, cancellationToken: cancellationToken);
        return Map<BrainStudy, BrainStudyDto>(study);
    }

    [Authorize(ResearchPermissions.BrainStudies.Update)]
    public virtual async Task<BrainStudyDto> ArchiveAsync(Guid id, ResearchCommandInput input, CancellationToken cancellationToken = default)
    {
        var study = await studies.GetAsync(id, cancellationToken: cancellationToken);
        CheckStamp(study.ConcurrencyStamp, input.ConcurrencyStamp);
        study.Archive(await HasActiveJobsAsync(id, cancellationToken));
        await studies.UpdateAsync(study, autoSave: true, cancellationToken: cancellationToken);
        return Map<BrainStudy, BrainStudyDto>(study);
    }

    [Authorize(ResearchPermissions.BrainStudies.Delete)]
    public virtual async Task DeleteAsync(Guid id, ResearchCommandInput input, CancellationToken cancellationToken = default)
    {
        var study = await studies.GetAsync(id, cancellationToken: cancellationToken);
        CheckStamp(study.ConcurrencyStamp, input.ConcurrencyStamp);
        study.EnsureCanDelete(await HasActiveJobsAsync(id, cancellationToken));
        await studies.DeleteAsync(study, autoSave: true, cancellationToken: cancellationToken);
    }

    private Task<bool> HasActiveJobsAsync(Guid studyId, CancellationToken cancellationToken) => jobs.AnyAsync(
        value => value.StudyId == studyId && (value.Status == SegmentationJobStatus.Pending || value.Status == SegmentationJobStatus.Running),
        cancellationToken);
}
