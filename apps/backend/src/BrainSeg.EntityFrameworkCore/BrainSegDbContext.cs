using BrainSeg.Research;
using Microsoft.EntityFrameworkCore;
using Volo.Abp.AuditLogging.EntityFrameworkCore;
using Volo.Abp.Data;
using Volo.Abp.EntityFrameworkCore;
using Volo.Abp.Identity.EntityFrameworkCore;
using Volo.Abp.OpenIddict.EntityFrameworkCore;
using Volo.Abp.PermissionManagement.EntityFrameworkCore;
using Volo.Abp.SettingManagement.EntityFrameworkCore;

namespace BrainSeg;

[ConnectionStringName("Default")]
public class BrainSegDbContext(DbContextOptions<BrainSegDbContext> options) : AbpDbContext<BrainSegDbContext>(options)
{
    public DbSet<BrainStudy> BrainStudies => Set<BrainStudy>();
    public DbSet<SegmentationJob> SegmentationJobs => Set<SegmentationJob>();
    public DbSet<ModelVersion> ModelVersions => Set<ModelVersion>();
    public DbSet<SegmentationResult> SegmentationResults => Set<SegmentationResult>();
    public DbSet<ExperimentRun> ExperimentRuns => Set<ExperimentRun>();

    protected override void OnModelCreating(ModelBuilder builder)
    {
        base.OnModelCreating(builder);
        builder.ConfigureIdentity();
        builder.ConfigureOpenIddict();
        builder.ConfigurePermissionManagement();
        builder.ConfigureSettingManagement();
        builder.ConfigureAuditLogging();
        builder.ConfigureResearch();
    }
}
