using Volo.Abp.AspNetCore.Mvc;
using Volo.Abp.Identity;
using Volo.Abp.Modularity;
using Volo.Abp.PermissionManagement.HttpApi;

namespace BrainSeg;

[DependsOn(typeof(BrainSegApplicationContractsModule), typeof(AbpAspNetCoreMvcModule),
    typeof(AbpIdentityHttpApiModule), typeof(AbpPermissionManagementHttpApiModule))]
public class BrainSegHttpApiModule : AbpModule;
