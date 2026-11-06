using Volo.Abp;
using Volo.Abp.Domain.Entities.Auditing;

namespace BrainSeg.Research;

public class ModelVersion : FullAuditedAggregateRoot<Guid>
{
    public string Name { get; private set; } = string.Empty;
    public string NormalizedName { get; private set; } = string.Empty;
    public ModelArchitecture Architecture { get; private set; }
    public string SemanticVersion { get; private set; } = string.Empty;
    public string PreprocessingVersion { get; private set; } = "flair-v1";
    public string WeightObjectKey { get; private set; } = string.Empty;
    public string WeightSha256 { get; private set; } = string.Empty;
    public int InputSize { get; private set; } = 256;
    public double Threshold { get; private set; }
    public string MetricsJson { get; private set; } = "{\"status\":\"NotRun\"}";
    public bool IsActive { get; private set; }
    public bool IsDefault { get; private set; }
    public DateTime? PublishedTime { get; private set; }

    protected ModelVersion() { }

    public ModelVersion(Guid id, string name, ModelArchitecture architecture, string semanticVersion,
        string weightObjectKey, string weightSha256, double threshold, string metricsJson) : base(id)
    {
        ResearchGuard.Identifier(id, nameof(Id));
        Name = ResearchGuard.Text(name, nameof(Name), 128);
        NormalizedName = Name.ToUpperInvariant();
        if (!Enum.IsDefined(architecture) || !double.IsFinite(threshold) || threshold is <= 0 or >= 1)
        {
            throw new BusinessException(ResearchErrors.InvalidInput);
        }
        Architecture = architecture;
        SemanticVersion = ResearchGuard.Version(semanticVersion);
        WeightObjectKey = ResearchGuard.ObjectKey(weightObjectKey, nameof(WeightObjectKey));
        WeightSha256 = ResearchGuard.Sha256(weightSha256, nameof(WeightSha256));
        Threshold = threshold;
        MetricsJson = ResearchGuard.MetricsJson(metricsJson);
    }

    public void Activate(DateTime now)
    {
        var publishedTime = ResearchGuard.Utc(now, PublishedTime);
        PublishedTime ??= publishedTime;
        IsActive = true;
    }

    public void MakeDefault()
    {
        EnsureActive();
        IsDefault = true;
    }

    public void ClearDefault() => IsDefault = false;

    public void Deactivate()
    {
        IsDefault = false;
        IsActive = false;
    }

    public void EnsureActive()
    {
        if (IsDeleted || !IsActive)
        {
            throw new BusinessException(ResearchErrors.ModelNotReady);
        }
    }
}
