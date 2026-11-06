using AutoMapper;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Volo.Abp.Application;
using Volo.Abp.AutoMapper;
using Volo.Abp.Identity;
using Volo.Abp.Modularity;
using Volo.Abp.PermissionManagement;

namespace BrainSeg;

[DependsOn(typeof(BrainSegDomainModule), typeof(BrainSegApplicationContractsModule),
    typeof(AbpDddApplicationModule), typeof(AbpIdentityApplicationModule),
    typeof(AbpPermissionManagementApplicationModule), typeof(AbpAutoMapperModule))]
public class BrainSegApplicationModule : AbpModule
{
    public override void ConfigureServices(ServiceConfigurationContext context)
    {
        Configure<AbpAutoMapperOptions>(options => options.AddMaps<BrainSegApplicationModule>(validate: true));
        context.Services.Replace(ServiceDescriptor.Singleton<global::AutoMapper.IConfigurationProvider>(provider =>
        {
            var expression = new MapperConfigurationExpression
            {
                LicenseKey = provider.GetRequiredService<IConfiguration>()["AutoMapper:LicenseKey"]
            };
            expression.ConstructServicesUsing(provider.GetRequiredService);
            var configurationContext = new AbpAutoMapperConfigurationContext(expression, provider);
            foreach (var configure in provider.GetRequiredService<IOptions<AbpAutoMapperOptions>>().Value.Configurators)
            {
                configure(configurationContext);
            }
            var configuration = new MapperConfiguration(expression, provider.GetRequiredService<ILoggerFactory>());
            configuration.AssertConfigurationIsValid();
            return configuration;
        }));
    }
}
