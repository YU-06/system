using System.Linq.Expressions;
using Volo.Abp;
using Volo.Abp.Application.Dtos;
using Volo.Abp.Application.Services;
using Volo.Abp.Data;
using Volo.Abp.Domain.Entities;

namespace BrainSeg.Research;

public abstract class ResearchAppService : ApplicationService
{
    protected ResearchAppService() => LocalizationResource = typeof(BrainSegResource);

    protected static void CheckStamp(string actual, string supplied)
    {
        if (string.IsNullOrWhiteSpace(supplied))
        {
            throw new BusinessException(ResearchErrors.InvalidInput).WithData("Field", "ConcurrencyStamp");
        }
        if (!string.Equals(actual, supplied, StringComparison.Ordinal))
        {
            throw new AbpDbConcurrencyException("The record has changed; reload it before retrying.");
        }
    }

    protected TDto Map<TEntity, TDto>(TEntity entity)
    {
        var dto = ObjectMapper.Map<TEntity, TDto>(entity);
        if (dto is SegmentationJobDto job && job.ErrorCode is not null)
        {
            job.ErrorMessage = L[job.ErrorCode];
        }
        return dto;
    }

    protected async Task<PagedResultDto<TDto>> PageAsync<TEntity, TDto>(IQueryable<TEntity> query,
        ResearchListInput input, IReadOnlyDictionary<string, Expression<Func<TEntity, object>>> fields,
        CancellationToken cancellationToken) where TEntity : IEntity<Guid>
    {
        if (input.SkipCount < 0 || input.MaxResultCount is < 1 or > 100 || input.Filter?.Length > 128
            || input.Sorting?.Length > 128)
        {
            throw new BusinessException(ResearchErrors.InvalidInput);
        }
        var parts = (input.Sorting ?? "creationTime desc").Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length is < 1 or > 2 || !fields.TryGetValue(parts[0], out var field)
            || parts.Length == 2 && !parts[1].Equals("asc", StringComparison.OrdinalIgnoreCase)
                && !parts[1].Equals("desc", StringComparison.OrdinalIgnoreCase))
        {
            throw new BusinessException(ResearchErrors.InvalidSorting);
        }
        var total = await AsyncExecuter.LongCountAsync(query, cancellationToken);
        var ordered = parts.Length == 2 && parts[1].Equals("desc", StringComparison.OrdinalIgnoreCase)
            ? query.OrderByDescending(field).ThenBy(entity => entity.Id)
            : query.OrderBy(field).ThenBy(entity => entity.Id);
        var entities = await AsyncExecuter.ToListAsync(ordered.Skip(input.SkipCount).Take(input.MaxResultCount), cancellationToken);
        return new PagedResultDto<TDto>(total, entities.Select(Map<TEntity, TDto>).ToList());
    }
}
