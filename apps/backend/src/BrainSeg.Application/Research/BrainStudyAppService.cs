using System.Linq.Expressions;
using BrainSeg.Storage;
using Microsoft.AspNetCore.Authorization;
using Microsoft.Extensions.Logging;
using Volo.Abp;
using Volo.Abp.Application.Dtos;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Uow;

namespace BrainSeg.Research;

[Authorize(ResearchPermissions.BrainStudies.Default)]
public class BrainStudyAppService(IBrainStudyRepository studies, ISegmentationJobRepository jobs,
    IObjectStorage storage, ResearchArtifactService artifacts, IUnitOfWorkManager unitOfWorkManager)
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
        var file = await artifacts.ReadStudyAsync(input.File, input.SliceIndex, cancellationToken);
        var candidate = new BrainStudy(GuidGenerator.Create(), input.StudyNumber, input.Pseudonym,
            "validation.bin", file.Sha256, file.Width, file.Height, input.SliceIndex);
        if (await studies.AnyAsync(value => value.StudyNumber == candidate.StudyNumber
            || value.OriginalFileSha256 == candidate.OriginalFileSha256 && value.SliceIndex == candidate.SliceIndex, cancellationToken))
        {
            throw new BusinessException(ResearchErrors.DuplicateStudy);
        }
        using var content = new MemoryStream(file.OriginalBytes, writable: false);
        var saved = await storage.SaveAsync(content, cancellationToken);
        var study = new BrainStudy(candidate.Id, candidate.StudyNumber, candidate.Pseudonym,
            saved.ObjectKey, saved.Sha256, file.Width, file.Height, input.SliceIndex);
        var cleanupDone = false;
        async Task CleanupAsync()
        {
            if (cleanupDone) return;
            cleanupDone = true;
            try { await storage.DeleteAsync(saved.ObjectKey, CancellationToken.None); }
            catch (Exception) { Logger.LogError("StudyUploadRollbackCleanupFailed for object {ObjectKey}", saved.ObjectKey); }
        }
        if (unitOfWorkManager.Current is { } unitOfWork)
        {
            unitOfWork.Failed += async (_, _) => await CleanupAsync();
        }
        try
        {
            study.MarkReady();
            await studies.InsertAsync(study, autoSave: true, cancellationToken: cancellationToken);
            return Map<BrainStudy, BrainStudyDto>(study);
        }
        catch
        {
            await CleanupAsync();
            throw;
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
