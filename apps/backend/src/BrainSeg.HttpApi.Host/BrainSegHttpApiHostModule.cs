using System.Security.Cryptography.X509Certificates;
using System.Threading.RateLimiting;
using BrainSeg.Hosting;
using BrainSeg.Storage;
using BrainSeg.System;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Diagnostics.HealthChecks;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.Extensions.DependencyInjection;
using OpenIddict.Server;
using OpenIddict.Validation.AspNetCore;
using Serilog;
using Volo.Abp;
using Volo.Abp.AspNetCore.ExceptionHandling;
using Volo.Abp.AspNetCore.Mvc;
using Volo.Abp.AspNetCore.Serilog;
using Volo.Abp.Auditing;
using Volo.Abp.Autofac;
using Volo.Abp.Identity.AspNetCore;
using Volo.Abp.Modularity;
using Volo.Abp.OpenIddict;
using Volo.Abp.Swashbuckle;

namespace BrainSeg;

[DependsOn(typeof(BrainSegApplicationModule), typeof(BrainSegEntityFrameworkCoreModule),
    typeof(BrainSegHttpApiModule), typeof(AbpAutofacModule), typeof(AbpAspNetCoreSerilogModule),
    typeof(AbpSwashbuckleModule), typeof(AbpIdentityAspNetCoreModule), typeof(AbpOpenIddictAspNetCoreModule))]
public class BrainSegHttpApiHostModule : AbpModule
{
    public override void PreConfigureServices(ServiceConfigurationContext context)
    {
        var environment = context.Services.GetHostingEnvironment();
        var configuration = context.Services.GetConfiguration();
        PreConfigure<AbpOpenIddictAspNetCoreOptions>(options =>
            options.AddDevelopmentEncryptionAndSigningCertificate = false);
        PreConfigure<OpenIddictServerBuilder>(server =>
        {
            if (environment.IsDevelopment() || environment.IsEnvironment("Testing"))
            {
                server.AddEphemeralEncryptionKey().AddEphemeralSigningKey();
                server.UseAspNetCore().DisableTransportSecurityRequirement();
            }
            else
            {
                var certificate = X509CertificateLoader.LoadPkcs12FromFile(
                    configuration["AuthServer:CertificatePath"]
                        ?? throw new InvalidOperationException("An OpenIddict certificate is required outside development."),
                    configuration["AuthServer:CertificatePassword"]);
                server.AddSigningCertificate(certificate).AddEncryptionCertificate(certificate);
            }
        });
        PreConfigure<OpenIddictBuilder>(builder => builder.AddValidation(options =>
        {
            options.UseLocalServer();
            options.UseAspNetCore();
        }));
    }

    public override void ConfigureServices(ServiceConfigurationContext context)
    {
        var configuration = context.Services.GetConfiguration();
        var services = context.Services;
        Configure<AbpAspNetCoreMvcOptions>(options =>
            options.ConventionalControllers.Create(typeof(SystemAppService).Assembly));
        Configure<AbpExceptionHandlingOptions>(options => options.SendExceptionsDetailsToClients = false);
        Configure<AbpAuditingOptions>(options => options.IsEnabledForAnonymousUsers = false);
        services.AddAuthentication(OpenIddictValidationAspNetCoreDefaults.AuthenticationScheme);
        services.Configure<RequestLocalizationOptions>(options => options
            .SetDefaultCulture("zh-Hans")
            .AddSupportedCultures("zh-Hans", "en")
            .AddSupportedUICultures("zh-Hans", "en"));
        services.AddAbpSwaggerGen(options =>
        {
            options.SwaggerDoc("v1", new()
            {
                Title = "BrainSeg Research API",
                Version = "v1",
                Description = ResearchScope.Disclaimer
            });
            options.DocInclusionPredicate((_, _) => true);
        });
        services.AddCors(options => options.AddDefaultPolicy(policy => policy
            .WithOrigins((configuration["App:CorsOrigins"] ?? "http://localhost:4200")
                .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            .AllowAnyHeader().AllowAnyMethod().WithExposedHeaders(SafeCorrelationMiddleware.HeaderName)));
        services.AddSingleton<IObjectStorage>(provider =>
            configuration["ObjectStorage:Provider"]?.Equals("Minio", StringComparison.OrdinalIgnoreCase) == true
                ? new MinioObjectStorage(configuration)
                : new LocalObjectStorage(configuration));
        services.AddTransient<CorrelationIdHandler>();
        services.AddHttpClient("ml-inference", client =>
        {
            client.BaseAddress = new Uri(configuration["MlInference:BaseUrl"] ?? "http://localhost:8000");
            client.Timeout = TimeSpan.FromSeconds(5);
        }).AddHttpMessageHandler<CorrelationIdHandler>();
        services.AddHealthChecks()
            .AddCheck<PostgreSqlHealthCheck>("postgresql", tags: ["ready"])
            .AddCheck<StorageHealthCheck>("object-storage", tags: ["ready"])
            .AddCheck<MlHealthCheck>("ml-inference", tags: ["ready"]);
        services.AddRateLimiter(options =>
        {
            options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
            options.GlobalLimiter = PartitionedRateLimiter.Create<HttpContext, string>(httpContext =>
                RateLimitPartition.GetFixedWindowLimiter(
                    httpContext.Connection.RemoteIpAddress?.ToString() ?? "unknown",
                    _ => new FixedWindowRateLimiterOptions
                    {
                        PermitLimit = 120,
                        Window = TimeSpan.FromMinutes(1),
                        QueueLimit = 0,
                        AutoReplenishment = true
                    }));
        });
        services.Configure<Microsoft.AspNetCore.Server.Kestrel.Core.KestrelServerOptions>(options =>
            options.Limits.MaxRequestBodySize = 64 * 1024 * 1024);
    }

    public override void OnApplicationInitialization(ApplicationInitializationContext context)
    {
        var app = context.GetApplicationBuilder();
        app.UseMiddleware<SafeCorrelationMiddleware>();
        app.UseCorrelationId();
        app.UseSerilogRequestLogging();
        app.UseRequestLocalization();
        app.UseRouting();
        app.UseCors();
        app.UseRateLimiter();
        app.UseAuthentication();
        app.UseAbpOpenIddictValidation();
        app.UseUnitOfWork();
        app.UseAuthorization();
        app.UseAuditing();
        app.UseSwagger();
        app.UseAbpSwaggerUI(options => options.SwaggerEndpoint("/swagger/v1/swagger.json", "BrainSeg v1"));
        app.UseAbpSerilogEnrichers();
        app.UseConfiguredEndpoints(endpoints =>
        {
            endpoints.MapHealthChecks("/health", new HealthCheckOptions
            {
                Predicate = _ => false,
                ResponseWriter = HealthResponseWriter.WriteAsync
            });
            endpoints.MapHealthChecks("/ready", new HealthCheckOptions
            {
                Predicate = registration => registration.Tags.Contains("ready"),
                ResponseWriter = HealthResponseWriter.WriteAsync
            });
        });
    }
}
