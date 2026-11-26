using Volo.Abp;
using Volo.Abp.Domain.Entities.Auditing;

namespace BrainSeg.Research;

public class BrainStudy : FullAuditedAggregateRoot<Guid>
{
    public string StudyNumber { get; private set; } = string.Empty;
    public string Pseudonym { get; private set; } = string.Empty;
    public string Modality { get; private set; } = ResearchScope.Modality;
    public string OriginalFileObjectKey { get; private set; } = string.Empty;
    public string OriginalFileSha256 { get; private set; } = string.Empty;
    public string? GroundTruthObjectKey { get; private set; }
    public string? GroundTruthSha256 { get; private set; }
    public bool HasGroundTruth => GroundTruthObjectKey is not null;
    public int Width { get; private set; }
    public int Height { get; private set; }
    public int SliceIndex { get; private set; }
    public BrainStudyStatus Status { get; private set; }
    public int JobRequestCount { get; private set; }

    protected BrainStudy() { }

    public BrainStudy(Guid id, string studyNumber, string pseudonym, string objectKey, string sha256,
        int width, int height, int sliceIndex) : base(id)
    {
        ResearchGuard.Identifier(id, nameof(Id));
        StudyNumber = ResearchGuard.Token(studyNumber, nameof(StudyNumber)).ToUpperInvariant();
        Pseudonym = ResearchGuard.Token(pseudonym, nameof(Pseudonym));
        OriginalFileObjectKey = ResearchGuard.ObjectKey(objectKey, nameof(OriginalFileObjectKey));
        OriginalFileSha256 = ResearchGuard.Sha256(sha256, nameof(OriginalFileSha256));
        if (width is < 1 or > 512 || height is < 1 or > 512 || sliceIndex is < 0 or > 511)
        {
            throw new BusinessException(ResearchErrors.InvalidInput);
        }
        Width = width;
        Height = height;
        SliceIndex = sliceIndex;
        Status = BrainStudyStatus.Uploaded;
    }

    public void MarkReady()
    {
        if (Status != BrainStudyStatus.Uploaded)
        {
            throw new BusinessException(ResearchErrors.IllegalStudyTransition);
        }
        Status = BrainStudyStatus.Ready;
    }

    public void ChangePseudonym(string pseudonym) => Pseudonym = ResearchGuard.Token(pseudonym, nameof(Pseudonym));

    public void RegisterGroundTruth(string objectKey, string sha256)
    {
        EnsureReady();
        if (GroundTruthObjectKey is not null)
            throw new BusinessException(ResearchErrors.GroundTruthAlreadyRegistered);
        GroundTruthObjectKey = ResearchGuard.ObjectKey(objectKey, nameof(GroundTruthObjectKey));
        GroundTruthSha256 = ResearchGuard.Sha256(sha256, nameof(GroundTruthSha256));
    }

    public string RemoveGroundTruth()
    {
        if (GroundTruthObjectKey is null)
            throw new BusinessException(ResearchErrors.GroundTruthNotRegistered);
        var objectKey = GroundTruthObjectKey;
        GroundTruthObjectKey = null;
        GroundTruthSha256 = null;
        return objectKey;
    }

    public void RecordJobRequest()
    {
        EnsureReady();
        JobRequestCount = checked(JobRequestCount + 1);
    }

    public void EnsureReady()
    {
        if (IsDeleted || Status != BrainStudyStatus.Ready)
        {
            throw new BusinessException(ResearchErrors.StudyNotReady);
        }
    }

    public void Archive(bool hasActiveJobs)
    {
        EnsureCanDelete(hasActiveJobs);
        if (Status != BrainStudyStatus.Ready)
        {
            throw new BusinessException(ResearchErrors.IllegalStudyTransition);
        }
        Status = BrainStudyStatus.Archived;
    }

    public void EnsureCanDelete(bool hasActiveJobs)
    {
        if (hasActiveJobs)
        {
            throw new BusinessException(ResearchErrors.StudyHasActiveJobs);
        }
    }
}
