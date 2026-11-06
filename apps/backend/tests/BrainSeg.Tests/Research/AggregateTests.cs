using BrainSeg.Research;
using Volo.Abp;
using Xunit;

namespace BrainSeg.Tests.Research;

public class AggregateTests
{
    internal static readonly string Hash = new('a', 64);
    internal static readonly DateTime Now = new(2026, 11, 6, 0, 0, 0, DateTimeKind.Utc);
    internal static string ObjectKey() => $"{Guid.NewGuid():N}.bin";
    internal static BrainStudy Study(string number = "study-001") =>
        new(Guid.NewGuid(), number, "case_001", ObjectKey(), Hash, 240, 240, 0);
    internal static ModelVersion Model(string name = "baseline") => new(Guid.NewGuid(), name,
        ModelArchitecture.UNet, "1.0.0", ObjectKey(), Hash, 0.5, "{\"status\":\"NotRun\"}");

    [Fact]
    public void Study_requires_verified_ready_state_and_preserves_a_job_reservation_version_change()
    {
        var study = Study();
        Assert.Equal("STUDY-001", study.StudyNumber);
        Assert.Throws<BusinessException>(study.RecordJobRequest);
        study.MarkReady();
        study.RecordJobRequest();
        Assert.Equal(1, study.JobRequestCount);
        Assert.Equal(ResearchErrors.StudyHasActiveJobs,
            Assert.Throws<BusinessException>(() => study.Archive(true)).Code);
        study.Archive(false);
        Assert.Equal(BrainStudyStatus.Archived, study.Status);
        Assert.Throws<BusinessException>(study.RecordJobRequest);
        Assert.Throws<BusinessException>(study.MarkReady);
    }

    [Fact]
    public void Inactive_model_cannot_be_default_and_deactivation_clears_default()
    {
        var model = Model();
        Assert.False(model.IsActive);
        Assert.Null(model.PublishedTime);
        Assert.Throws<BusinessException>(model.MakeDefault);
        model.Activate(Now);
        model.MakeDefault();
        model.Deactivate();
        Assert.False(model.IsDefault);
        Assert.False(model.IsActive);
        Assert.Equal(Now, model.PublishedTime);
        model.Activate(Now.AddSeconds(1));
        Assert.Equal(Now, model.PublishedTime);
    }

    [Fact]
    public void Results_without_ground_truth_keep_metrics_null_and_compute_area_ratio()
    {
        var result = new SegmentationResult(Guid.NewGuid(), Guid.NewGuid(), ObjectKey(), ObjectKey(),
            ObjectKey(), 32768, 10, 2, 1, Now);
        Assert.Null(result.Dice);
        Assert.Null(result.IoU);
        Assert.Equal(0.5, result.TumorAreaRatio);
        Assert.Throws<BusinessException>(() => new SegmentationResult(Guid.NewGuid(), Guid.NewGuid(),
            ObjectKey(), ObjectKey(), ObjectKey(), 1, 0, 0, 0, Now, dice: 1));
        Assert.Throws<BusinessException>(() => new SegmentationResult(Guid.NewGuid(), Guid.NewGuid(),
            ObjectKey(), ObjectKey(), ObjectKey(), 65537, 0, 0, 0, Now));
    }

    [Fact]
    public void Invalid_paths_hashes_models_and_metrics_are_rejected()
    {
        Assert.Throws<BusinessException>(() => new BrainStudy(Guid.NewGuid(), "S-1", "case-1",
            "../private.nii", Hash, 240, 240, 0));
        Assert.Throws<BusinessException>(() => new ModelVersion(Guid.NewGuid(), "baseline",
            ModelArchitecture.UNet, "invalid", ObjectKey(), Hash, 0.5, "{}"));
        Assert.Throws<BusinessException>(() => new ModelVersion(Guid.NewGuid(), "baseline",
            ModelArchitecture.UNet, "1.0.0", ObjectKey(), Hash, double.NaN, "{}"));
        Assert.Throws<BusinessException>(() => new ModelVersion(Guid.NewGuid(), "baseline",
            ModelArchitecture.UNet, "1.0.0", ObjectKey(), Hash, 0.5, "[]"));
        Assert.Throws<BusinessException>(() => new ExperimentRun(Guid.NewGuid(), "seed-run", Hash,
            "not-a-commit", Hash, 42, Guid.NewGuid(), "{}", ObjectKey(), Now));
    }
}
