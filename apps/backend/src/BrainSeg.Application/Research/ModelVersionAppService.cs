using System.Linq.Expressions;
using Microsoft.AspNetCore.Authorization;
using Volo.Abp;
using Volo.Abp.Application.Dtos;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.Uow;

namespace BrainSeg.Research;

[Authorize(ResearchPermissions.ModelVersions.Default)]
public class ModelVersionAppService(IModelVersionRepository models, ResearchArtifactService artifacts)
    : ResearchAppService, IModelVersionAppService
{
    private static readonly IReadOnlyDictionary<string, Expression<Func<ModelVersion, object>>> Sorting =
        new Dictionary<string, Expression<Func<ModelVersion, object>>>(StringComparer.OrdinalIgnoreCase)
        {
            ["creationTime"] = value => value.CreationTime,
            ["name"] = value => value.Name,
            ["semanticVersion"] = value => value.SemanticVersion,
            ["architecture"] = value => value.Architecture
        };

    public virtual async Task<ModelVersionDto> GetAsync(Guid id, CancellationToken cancellationToken = default) =>
        Map<ModelVersion, ModelVersionDto>(await models.GetAsync(id, cancellationToken: cancellationToken));

    public virtual async Task<PagedResultDto<ModelVersionDto>> GetListAsync(ModelVersionListInput input, CancellationToken cancellationToken = default)
    {
        var query = await models.GetQueryableAsync();
        if (input.Architecture.HasValue) query = query.Where(value => value.Architecture == input.Architecture);
        if (input.IsActive.HasValue) query = query.Where(value => value.IsActive == input.IsActive);
        if (!string.IsNullOrWhiteSpace(input.Filter))
        {
            var filter = input.Filter.Trim().ToLowerInvariant();
            query = query.Where(value => value.Name.ToLower().Contains(filter) || value.SemanticVersion.ToLower().Contains(filter));
        }
        return await PageAsync<ModelVersion, ModelVersionDto>(query, input, Sorting, cancellationToken);
    }

    [Authorize(ResearchPermissions.ModelVersions.Create)]
    public virtual async Task<ModelVersionDto> CreateAsync(CreateModelVersionInput input, CancellationToken cancellationToken = default)
    {
        var model = new ModelVersion(GuidGenerator.Create(), input.Name, input.Architecture, input.SemanticVersion,
            input.WeightObjectKey, input.WeightSha256, input.Threshold, input.MetricsJson);
        if (await models.AnyAsync(value => value.Architecture == model.Architecture
            && value.NormalizedName == model.NormalizedName && value.SemanticVersion == model.SemanticVersion, cancellationToken))
            throw new BusinessException(ResearchErrors.DuplicateModelVersion);
        await artifacts.VerifyAsync(model.WeightObjectKey, model.WeightSha256, cancellationToken);
        await models.InsertAsync(model, autoSave: true, cancellationToken: cancellationToken);
        return Map<ModelVersion, ModelVersionDto>(model);
    }

    [Authorize(ResearchPermissions.ModelVersions.Manage)]
    [UnitOfWork(isTransactional: true)]
    public virtual async Task<ModelVersionDto> SetStateAsync(Guid id, ChangeModelStateInput input, CancellationToken cancellationToken = default)
    {
        var model = await models.GetAsync(id, cancellationToken: cancellationToken);
        CheckStamp(model.ConcurrencyStamp, input.ConcurrencyStamp);
        if (!input.IsActive)
        {
            if (input.IsDefault) throw new BusinessException(ResearchErrors.ModelNotReady);
            model.Deactivate();
        }
        else
        {
            await artifacts.VerifyAsync(model.WeightObjectKey, model.WeightSha256, cancellationToken);
            model.Activate(Clock.Now);
            if (input.IsDefault)
            {
                var previous = await models.GetListAsync(value => value.IsDefault && value.Id != id, cancellationToken: cancellationToken);
                foreach (var old in previous)
                {
                    old.ClearDefault();
                    await models.UpdateAsync(old, autoSave: true, cancellationToken: cancellationToken);
                }
                model.MakeDefault();
            }
            else model.ClearDefault();
        }
        await models.UpdateAsync(model, autoSave: true, cancellationToken: cancellationToken);
        return Map<ModelVersion, ModelVersionDto>(model);
    }
}
