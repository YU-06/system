using System.Linq.Expressions;
using Microsoft.AspNetCore.Authorization;
using Volo.Abp.Application.Dtos;

namespace BrainSeg.Research;

[Authorize(ResearchPermissions.SegmentationResults.Default)]
public class SegmentationResultAppService(ISegmentationResultRepository results, ISegmentationJobRepository jobs)
    : ResearchAppService, ISegmentationResultAppService
{
    private static readonly IReadOnlyDictionary<string, Expression<Func<SegmentationResult, object>>> Sorting =
        new Dictionary<string, Expression<Func<SegmentationResult, object>>>(StringComparer.OrdinalIgnoreCase)
        {
            ["creationTime"] = value => value.CreationTime,
            ["createdTime"] = value => value.CreatedTime,
            ["inferenceMilliseconds"] = value => value.InferenceMilliseconds,
            ["tumorAreaPixels"] = value => value.TumorAreaPixels
        };

    public virtual async Task<SegmentationResultDto> GetAsync(Guid id, CancellationToken cancellationToken = default) =>
        Map<SegmentationResult, SegmentationResultDto>(await results.GetAsync(id, cancellationToken: cancellationToken));

    public virtual async Task<PagedResultDto<SegmentationResultDto>> GetListAsync(SegmentationResultListInput input, CancellationToken cancellationToken = default)
    {
        var query = await results.GetQueryableAsync();
        if (input.JobId.HasValue) query = query.Where(value => value.JobId == input.JobId);
        if (!string.IsNullOrWhiteSpace(input.Filter))
        {
            var filter = input.Filter.Trim().ToLowerInvariant();
            var matchingJobs = (await jobs.GetQueryableAsync()).Where(job => job.CorrelationId.ToLower().Contains(filter)).Select(job => job.Id);
            query = query.Where(value => matchingJobs.Contains(value.JobId));
        }
        return await PageAsync<SegmentationResult, SegmentationResultDto>(query, input, Sorting, cancellationToken);
    }
}
