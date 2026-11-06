using Volo.Abp;
using Volo.Abp.Domain.Entities.Auditing;

namespace BrainSeg.Research;

public class ExperimentRun : FullAuditedAggregateRoot<Guid>
{
    public string ExperimentName { get; private set; } = string.Empty;
    public string ConfigHash { get; private set; } = string.Empty;
    public string GitCommit { get; private set; } = string.Empty;
    public string DatasetSplitHash { get; private set; } = string.Empty;
    public int RandomSeed { get; private set; }
    public Guid ModelVersionId { get; private set; }
    public string MetricsJson { get; private set; } = string.Empty;
    public string ArtifactObjectKey { get; private set; } = string.Empty;
    public DateTime CreatedTime { get; private set; }

    protected ExperimentRun() { }

    public ExperimentRun(Guid id, string experimentName, string configHash, string gitCommit,
        string datasetSplitHash, int randomSeed, Guid modelVersionId, string metricsJson,
        string artifactObjectKey, DateTime createdTime) : base(id)
    {
        ResearchGuard.Identifier(id, nameof(Id));
        ExperimentName = ResearchGuard.Text(experimentName, nameof(ExperimentName), 128);
        ConfigHash = ResearchGuard.Sha256(configHash, nameof(ConfigHash));
        DatasetSplitHash = ResearchGuard.Sha256(datasetSplitHash, nameof(DatasetSplitHash));
        if (gitCommit.Length is not (40 or 64) || !gitCommit.All(Uri.IsHexDigit) || randomSeed < 0)
        {
            throw new BusinessException(ResearchErrors.InvalidInput);
        }
        GitCommit = gitCommit.ToLowerInvariant();
        RandomSeed = randomSeed;
        ModelVersionId = ResearchGuard.Identifier(modelVersionId, nameof(ModelVersionId));
        MetricsJson = ResearchGuard.MetricsJson(metricsJson);
        ArtifactObjectKey = ResearchGuard.ObjectKey(artifactObjectKey, nameof(ArtifactObjectKey));
        CreatedTime = ResearchGuard.Utc(createdTime);
    }
}
