using System.Security.Claims;
using System.Text.Encodings.Web;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Volo.Abp.Auditing;
using Volo.Abp.Authorization.Permissions;
using Volo.Abp.EntityFrameworkCore;
using Volo.Abp.Security.Claims;
using Volo.Abp.Uow;

namespace BrainSeg.Tests.Research;

public class ResearchFactory : BrainSegFactory, IResearchTestDatabase
{
    private readonly SqliteConnection connection;
    private readonly string storagePath = Path.Combine(Path.GetTempPath(), "brainseg-research-tests", Guid.NewGuid().ToString("N"));
    public static readonly Guid UserId = Guid.Parse("22222222-2222-2222-2222-222222222222");

    public ResearchFactory()
    {
        connection = new SqliteConnection($"Data Source=brainseg-{Guid.NewGuid():N};Mode=Memory;Cache=Shared");
        connection.Open();
    }

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        base.ConfigureWebHost(builder);
        builder.ConfigureAppConfiguration((_, configuration) => configuration.AddInMemoryCollection(
            new Dictionary<string, string?>
            {
                ["ConnectionStrings:Default"] = connection.ConnectionString,
                ["ObjectStorage:RootPath"] = storagePath
            }));
        builder.ConfigureTestServices(services =>
        {
            services.PostConfigure<AbpDbContextOptions>(options =>
            {
                options.Configure(context => context.DbContextOptions.UseSqlite(connection.ConnectionString));
                options.Configure<BrainSegDbContext>(context => context.DbContextOptions.UseSqlite(connection.ConnectionString));
            });
            services.Replace(ServiceDescriptor.Transient<IPermissionChecker, ResearchTestPermissionChecker>());
            services.Replace(ServiceDescriptor.Singleton<IAuditingStore, ResearchTestAuditingStore>());
            services.AddAuthentication(options =>
            {
                options.DefaultAuthenticateScheme = "ResearchTest";
                options.DefaultChallengeScheme = "ResearchTest";
                options.DefaultForbidScheme = "ResearchTest";
            }).AddScheme<AuthenticationSchemeOptions, ResearchTestAuthenticationHandler>("ResearchTest", _ => { });
        });
    }

    public Task InitializeAsync() => RunAsync(async services =>
        await (await services.GetRequiredService<IDbContextProvider<BrainSegDbContext>>().GetDbContextAsync())
            .Database.EnsureCreatedAsync());

    public async Task RunAsync(Func<IServiceProvider, Task> action)
    {
        using var scope = Services.CreateScope();
        using var unitOfWork = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>()
            .Begin(requiresNew: true, isTransactional: false);
        await action(scope.ServiceProvider);
        await unitOfWork.CompleteAsync();
    }

    public HttpClient AuthenticatedClient(params string[] permissions)
    {
        var client = CreateClient();
        client.DefaultRequestHeaders.Add("X-Research-Test-User", UserId.ToString());
        client.DefaultRequestHeaders.Add("X-Research-Test-Permissions", string.Join(',', permissions));
        return client;
    }

    protected override void Dispose(bool disposing)
    {
        base.Dispose(disposing);
        if (disposing)
        {
            connection.Dispose();
            if (Directory.Exists(storagePath)) Directory.Delete(storagePath, recursive: true);
        }
    }
}

public class ResearchTestPermissionChecker(ICurrentPrincipalAccessor accessor) : IPermissionChecker
{
    public Task<bool> IsGrantedAsync(string name) => IsGrantedAsync(accessor.Principal, name);
    public Task<bool> IsGrantedAsync(ClaimsPrincipal? principal, string name) =>
        Task.FromResult(principal?.Identity?.IsAuthenticated == true && principal.HasClaim("research-permission", name));

    public Task<MultiplePermissionGrantResult> IsGrantedAsync(string[] names) => IsGrantedAsync(accessor.Principal, names);

    public Task<MultiplePermissionGrantResult> IsGrantedAsync(ClaimsPrincipal? principal, string[] names)
    {
        var result = new MultiplePermissionGrantResult(names);
        foreach (var name in names)
        {
            result.Result[name] = principal?.Identity?.IsAuthenticated == true && principal.HasClaim("research-permission", name)
                ? PermissionGrantResult.Granted : PermissionGrantResult.Prohibited;
        }
        return Task.FromResult(result);
    }
}

public class ResearchTestAuthenticationHandler(IOptionsMonitor<AuthenticationSchemeOptions> options,
    ILoggerFactory logger, UrlEncoder encoder) : AuthenticationHandler<AuthenticationSchemeOptions>(options, logger, encoder)
{
    protected override Task<AuthenticateResult> HandleAuthenticateAsync()
    {
        if (!Guid.TryParse(Request.Headers["X-Research-Test-User"], out var id))
            return Task.FromResult(AuthenticateResult.NoResult());
        var claims = new List<Claim> { new(AbpClaimTypes.UserId, id.ToString()), new(AbpClaimTypes.UserName, "research-test") };
        claims.AddRange(Request.Headers["X-Research-Test-Permissions"].ToString().Split(',', StringSplitOptions.RemoveEmptyEntries)
            .Select(permission => new Claim("research-permission", permission)));
        var principal = new ClaimsPrincipal(new ClaimsIdentity(claims, Scheme.Name));
        return Task.FromResult(AuthenticateResult.Success(new AuthenticationTicket(principal, Scheme.Name)));
    }
}

public class ResearchTestAuditingStore : IAuditingStore
{
    public global::System.Collections.Concurrent.ConcurrentBag<AuditLogInfo> Entries { get; } = [];

    public Task SaveAsync(AuditLogInfo auditInfo)
    {
        Entries.Add(auditInfo);
        return Task.CompletedTask;
    }
}

public interface IResearchTestDatabase : IDisposable
{
    IServiceProvider Services { get; }
    Task InitializeAsync();
    Task RunAsync(Func<IServiceProvider, Task> action);
}
