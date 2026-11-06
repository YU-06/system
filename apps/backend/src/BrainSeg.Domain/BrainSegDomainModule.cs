using Volo.Abp.Domain;
using Volo.Abp.Identity;
using Volo.Abp.Modularity;
using Volo.Abp.OpenIddict;
using Volo.Abp.PermissionManagement.Identity;
using Volo.Abp.Timing;

namespace BrainSeg;

[DependsOn(typeof(BrainSegDomainSharedModule), typeof(AbpDddDomainModule),
    typeof(AbpIdentityDomainModule), typeof(AbpOpenIddictDomainModule),
    typeof(AbpPermissionManagementDomainIdentityModule))]
public class BrainSegDomainModule : AbpModule
{
    public override void ConfigureServices(ServiceConfigurationContext context)
    {
        Configure<AbpClockOptions>(options => options.Kind = DateTimeKind.Utc);
    }
}
