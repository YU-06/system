using BrainSeg.Research;
using Microsoft.Extensions.DependencyInjection;
using Volo.Abp.AuditLogging.EntityFrameworkCore;
using Volo.Abp.EntityFrameworkCore;
using Volo.Abp.EntityFrameworkCore.PostgreSql;
using Volo.Abp.Identity.EntityFrameworkCore;
using Volo.Abp.Modularity;
using Volo.Abp.OpenIddict.EntityFrameworkCore;
using Volo.Abp.PermissionManagement;
using Volo.Abp.PermissionManagement.EntityFrameworkCore;
using Volo.Abp.SettingManagement;
using Volo.Abp.SettingManagement.EntityFrameworkCore;

namespace BrainSeg;

[DependsOn(typeof(BrainSegDomainModule), typeof(AbpEntityFrameworkCorePostgreSqlModule),
    typeof(AbpIdentityEntityFrameworkCoreModule), typeof(AbpOpenIddictEntityFrameworkCoreModule),
    typeof(AbpPermissionManagementEntityFrameworkCoreModule), typeof(AbpSettingManagementEntityFrameworkCoreModule),
    typeof(AbpAuditLoggingEntityFrameworkCoreModule))]
public class BrainSegEntityFrameworkCoreModule : AbpModule
{
    public override void ConfigureServices(ServiceConfigurationContext context)
    {
        context.Services.AddAbpDbContext<BrainSegDbContext>();
        context.Services.AddTransient<IBrainStudyRepository, EfCoreBrainStudyRepository>();
        context.Services.AddTransient<ISegmentationJobRepository, EfCoreSegmentationJobRepository>();
        context.Services.AddTransient<IModelVersionRepository, EfCoreModelVersionRepository>();
        context.Services.AddTransient<ISegmentationResultRepository, EfCoreSegmentationResultRepository>();
        context.Services.AddTransient<IExperimentRunRepository, EfCoreExperimentRunRepository>();
        Configure<AbpDbContextOptions>(options => options.UseNpgsql());
        Configure<PermissionManagementOptions>(options =>
        {
            options.SaveStaticPermissionsToDatabase = false;
            options.IsDynamicPermissionStoreEnabled = false;
        });
        Configure<SettingManagementOptions>(options =>
        {
            options.SaveStaticSettingsToDatabase = false;
            options.IsDynamicSettingStoreEnabled = false;
        });
    }
}
