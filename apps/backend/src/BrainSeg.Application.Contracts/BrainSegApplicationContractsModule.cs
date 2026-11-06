using Volo.Abp.Application;
using Volo.Abp.Identity;
using Volo.Abp.Modularity;
using Volo.Abp.PermissionManagement;

namespace BrainSeg;

[DependsOn(typeof(BrainSegDomainSharedModule), typeof(AbpDddApplicationContractsModule),
    typeof(AbpIdentityApplicationContractsModule), typeof(AbpPermissionManagementApplicationContractsModule))]
public class BrainSegApplicationContractsModule : AbpModule;
