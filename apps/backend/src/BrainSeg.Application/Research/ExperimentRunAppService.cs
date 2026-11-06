using System.Linq.Expressions;
using Microsoft.AspNetCore.Authorization;
using Volo.Abp;
using Volo.Abp.Application.Dtos;
using Volo.Abp.Domain.Repositories;

namespace BrainSeg.Research;

[Authorize(ResearchPermissions.ExperimentRuns.Default)]
public class ExperimentRunAppService(IExperimentRunRepository experiments, IModelVersionRepository models,
    ResearchArtifactService artifacts) : ResearchAppService, IExperimentRunAppService
{
    private static readonly IReadOnlyDictionary<string, Expression<Func<ExperimentRun, object>>> Sorting =
        new Dictionary<string, Expression<Func<ExperimentRun, object>>>(StringComparer.OrdinalIgnoreCase)
        {
            ["creationTime"] = value => value.CreationTime,
            ["createdTime"] = value => value.CreatedTime,
            ["experimentName"] = value => value.ExperimentName,
            ["randomSeed"] = value => value.RandomSeed
        };

    public virtual async Task<ExperimentRunDto> GetAsync(Guid id, CancellationToken cancellationToken = default) =>
        Map<ExperimentRun, ExperimentRunDto>(await experiments.GetAsync(id, cancellationToken: cancellationToken));

    public virtual async Task<PagedResultDto<ExperimentRunDto>> GetListAsync(ExperimentRunListInput input, CancellationToken cancellationToken = default)
    {
        var query = await experiments.GetQueryableAsync();
        if (input.ModelVersionId.HasValue) query = query.Where(value => value.ModelVersionId == input.ModelVersionId);
        if (input.RandomSeed.HasValue) query = query.Where(value => value.RandomSeed == input.RandomSeed);
        if (!string.IsNullOrWhiteSpace(input.Filter))
        {
            var filter = input.Filter.Trim().ToLowerInvariant();
            query = query.Where(value => value.ExperimentName.ToLower().Contains(filter));
        }
        return await PageAsync<ExperimentRun, ExperimentRunDto>(query, input, Sorting, cancellationToken);
    }

    [Authorize(ResearchPermissions.ExperimentRuns.Create)]
    public virtual async Task<ExperimentRunDto> CreateAsync(CreateExperimentRunInput input, CancellationToken cancellationToken = default)
    {
        var run = new ExperimentRun(GuidGenerator.Create(), input.ExperimentName, input.ConfigHash, input.GitCommit,
            input.DatasetSplitHash, input.RandomSeed, input.ModelVersionId, input.MetricsJson, input.ArtifactObjectKey, Clock.Now);
        await models.GetAsync(run.ModelVersionId, cancellationToken: cancellationToken);
        if (await experiments.AnyAsync(value => value.ExperimentName == run.ExperimentName && value.ConfigHash == run.ConfigHash
            && value.DatasetSplitHash == run.DatasetSplitHash && value.GitCommit == run.GitCommit
            && value.RandomSeed == run.RandomSeed && value.ModelVersionId == run.ModelVersionId, cancellationToken))
            throw new BusinessException(ResearchErrors.DuplicateExperiment);
        await artifacts.VerifyAsync(run.ArtifactObjectKey, null, cancellationToken);
        await experiments.InsertAsync(run, autoSave: true, cancellationToken: cancellationToken);
        return Map<ExperimentRun, ExperimentRunDto>(run);
    }
}
