using Volo.Abp.Application;
using Volo.Abp.Identity;
using Volo.Abp.Modularity;
using Volo.Abp.PermissionManagement;

namespace BrainSeg;

[DependsOn(typeof(BrainSegDomainModule), typeof(BrainSegApplicationContractsModule),
    typeof(AbpDddApplicationModule), typeof(AbpIdentityApplicationModule),
    typeof(AbpPermissionManagementApplicationModule))]
public class BrainSegApplicationModule : AbpModule;
