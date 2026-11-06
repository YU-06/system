using Volo.Abp.Domain;
using Volo.Abp.Modularity;

namespace BrainSeg;

[DependsOn(typeof(AbpDddDomainSharedModule))]
public class BrainSegDomainSharedModule : AbpModule;
