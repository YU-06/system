using BrainSeg.Research;
using Volo.Abp.Domain;
using Volo.Abp.Localization;
using Volo.Abp.Localization.ExceptionHandling;
using Volo.Abp.Modularity;
using Volo.Abp.VirtualFileSystem;

namespace BrainSeg;

[DependsOn(typeof(AbpDddDomainSharedModule))]
public class BrainSegDomainSharedModule : AbpModule
{
    public override void ConfigureServices(ServiceConfigurationContext context)
    {
        Configure<AbpVirtualFileSystemOptions>(options => options.FileSets.AddEmbedded<BrainSegDomainSharedModule>());
        Configure<AbpLocalizationOptions>(options => options.Resources.Add<BrainSegResource>("en")
            .AddVirtualJson("/Localization/BrainSeg"));
        Configure<AbpExceptionLocalizationOptions>(options => options.MapCodeNamespace("BrainSeg", typeof(BrainSegResource)));
    }
}
