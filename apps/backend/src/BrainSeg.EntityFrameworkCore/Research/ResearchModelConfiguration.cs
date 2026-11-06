using Microsoft.EntityFrameworkCore;
using Volo.Abp.EntityFrameworkCore.Modeling;

namespace BrainSeg.Research;

public static class ResearchModelConfiguration
{
    public static void ConfigureResearch(this ModelBuilder builder)
    {
        builder.Entity<BrainStudy>(entity =>
        {
            entity.ToTable("BrainStudies", table => table.HasCheckConstraint("CK_BrainStudies_Dimensions",
                "\"Width\" BETWEEN 1 AND 512 AND \"Height\" BETWEEN 1 AND 512 AND \"SliceIndex\" BETWEEN 0 AND 511 AND \"JobRequestCount\" >= 0"));
            entity.ConfigureByConvention();
            entity.Property(value => value.StudyNumber).IsRequired().HasMaxLength(64);
            entity.Property(value => value.Pseudonym).IsRequired().HasMaxLength(64);
            entity.Property(value => value.Modality).IsRequired().HasMaxLength(16);
            entity.Property(value => value.OriginalFileObjectKey).IsRequired().HasMaxLength(512);
            entity.Property(value => value.OriginalFileSha256).IsRequired().HasMaxLength(64);
            entity.HasIndex(value => value.StudyNumber).IsUnique().HasFilter("\"IsDeleted\" = false")
                .HasDatabaseName("UX_BrainStudies_Number");
            entity.HasIndex(value => new { value.OriginalFileSha256, value.SliceIndex }).IsUnique()
                .HasFilter("\"IsDeleted\" = false").HasDatabaseName("UX_BrainStudies_FileSlice");
            entity.HasIndex(value => new { value.Status, value.CreationTime });
        });

        builder.Entity<ModelVersion>(entity =>
        {
            entity.ToTable("ModelVersions", table =>
            {
                table.HasCheckConstraint("CK_ModelVersions_Protocol", "\"InputSize\" = 256 AND \"Threshold\" > 0 AND \"Threshold\" < 1");
                table.HasCheckConstraint("CK_ModelVersions_Default", "\"IsDefault\" = false OR \"IsActive\" = true");
            });
            entity.ConfigureByConvention();
            entity.Property(value => value.Name).IsRequired().HasMaxLength(128);
            entity.Property(value => value.NormalizedName).IsRequired().HasMaxLength(128);
            entity.Property(value => value.SemanticVersion).IsRequired().HasMaxLength(64);
            entity.Property(value => value.PreprocessingVersion).IsRequired().HasMaxLength(32);
            entity.Property(value => value.WeightObjectKey).IsRequired().HasMaxLength(512);
            entity.Property(value => value.WeightSha256).IsRequired().HasMaxLength(64);
            entity.Property(value => value.MetricsJson).IsRequired().HasMaxLength(16384);
            entity.HasIndex(value => new { value.Architecture, value.NormalizedName, value.SemanticVersion })
                .IsUnique().HasFilter("\"IsDeleted\" = false").HasDatabaseName("UX_ModelVersions_Identity");
            entity.HasIndex(value => value.IsDefault).IsUnique()
                .HasFilter("\"IsDefault\" = true AND \"IsDeleted\" = false").HasDatabaseName("UX_ModelVersions_Default");
            entity.HasIndex(value => new { value.IsActive, value.Architecture });
        });

        builder.Entity<SegmentationJob>(entity =>
        {
            entity.ToTable("SegmentationJobs", table =>
            {
                table.HasCheckConstraint("CK_SegmentationJobs_Progress", "\"Progress\" BETWEEN 0 AND 100");
                table.HasCheckConstraint("CK_SegmentationJobs_RetryCount", "\"RetryCount\" BETWEEN 0 AND 3");
            });
            entity.ConfigureByConvention();
            entity.Property(value => value.IdempotencyKey).IsRequired().HasMaxLength(128);
            entity.Property(value => value.CorrelationId).IsRequired().HasMaxLength(64);
            entity.Property(value => value.ErrorCode).HasMaxLength(128);
            entity.Property(value => value.ErrorMessage).HasMaxLength(256);
            entity.HasIndex(value => new { value.RequesterId, value.IdempotencyKey }).IsUnique()
                .HasDatabaseName("UX_SegmentationJobs_Idempotency");
            entity.HasIndex(value => new { value.Status, value.RequestedTime });
            entity.HasIndex(value => new { value.StudyId, value.Status });
            entity.HasOne<BrainStudy>().WithMany().HasForeignKey(value => value.StudyId).OnDelete(DeleteBehavior.Restrict);
            entity.HasOne<ModelVersion>().WithMany().HasForeignKey(value => value.ModelVersionId).OnDelete(DeleteBehavior.Restrict);
        });

        builder.Entity<SegmentationResult>(entity =>
        {
            entity.ToTable("SegmentationResults", table =>
            {
                table.HasCheckConstraint("CK_SegmentationResults_Area", "\"TumorAreaPixels\" BETWEEN 0 AND 65536 AND \"TumorAreaRatio\" BETWEEN 0 AND 1");
                table.HasCheckConstraint("CK_SegmentationResults_Timings", "\"InferenceMilliseconds\" >= 0 AND \"PreprocessingMilliseconds\" >= 0 AND \"PostprocessingMilliseconds\" >= 0");
                table.HasCheckConstraint("CK_SegmentationResults_Metrics", "(\"Dice\" IS NULL OR \"Dice\" BETWEEN 0 AND 1) AND (\"IoU\" IS NULL OR \"IoU\" BETWEEN 0 AND 1) AND (\"Precision\" IS NULL OR \"Precision\" BETWEEN 0 AND 1) AND (\"Recall\" IS NULL OR \"Recall\" BETWEEN 0 AND 1)");
            });
            entity.ConfigureByConvention();
            entity.Property(value => value.MaskObjectKey).IsRequired().HasMaxLength(512);
            entity.Property(value => value.OverlayObjectKey).IsRequired().HasMaxLength(512);
            entity.Property(value => value.ContourObjectKey).IsRequired().HasMaxLength(512);
            entity.HasIndex(value => value.JobId).IsUnique().HasDatabaseName("UX_SegmentationResults_Job");
            entity.HasIndex(value => value.CreatedTime);
            entity.HasOne<SegmentationJob>().WithMany().HasForeignKey(value => value.JobId).OnDelete(DeleteBehavior.Restrict);
        });

        builder.Entity<ExperimentRun>(entity =>
        {
            entity.ToTable("ExperimentRuns", table => table.HasCheckConstraint("CK_ExperimentRuns_Seed", "\"RandomSeed\" >= 0"));
            entity.ConfigureByConvention();
            entity.Property(value => value.ExperimentName).IsRequired().HasMaxLength(128);
            entity.Property(value => value.ConfigHash).IsRequired().HasMaxLength(64);
            entity.Property(value => value.GitCommit).IsRequired().HasMaxLength(64);
            entity.Property(value => value.DatasetSplitHash).IsRequired().HasMaxLength(64);
            entity.Property(value => value.MetricsJson).IsRequired().HasMaxLength(16384);
            entity.Property(value => value.ArtifactObjectKey).IsRequired().HasMaxLength(512);
            entity.HasIndex(value => new { value.ExperimentName, value.ConfigHash, value.DatasetSplitHash, value.GitCommit, value.RandomSeed, value.ModelVersionId })
                .IsUnique().HasDatabaseName("UX_ExperimentRuns_Reproducibility");
            entity.HasIndex(value => value.CreatedTime);
            entity.HasOne<ModelVersion>().WithMany().HasForeignKey(value => value.ModelVersionId).OnDelete(DeleteBehavior.Restrict);
        });
    }
}
