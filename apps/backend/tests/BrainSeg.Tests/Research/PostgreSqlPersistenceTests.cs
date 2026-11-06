using BrainSeg.Research;
using Microsoft.AspNetCore.Hosting;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;
using Volo.Abp;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.EntityFrameworkCore;
using Volo.Abp.Uow;
using Xunit;

namespace BrainSeg.Tests.Research;

public sealed class PostgreSqlFactAttribute : FactAttribute
{
    public PostgreSqlFactAttribute()
    {
        if (string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("BRAINSEG_TEST_POSTGRES")))
            Skip = "BRAINSEG_TEST_POSTGRES is not configured; PostgreSQL integration was not run.";
    }
}

public sealed class PostgreSqlTheoryAttribute : TheoryAttribute
{
    public PostgreSqlTheoryAttribute()
    {
        if (string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("BRAINSEG_TEST_POSTGRES")))
            Skip = "BRAINSEG_TEST_POSTGRES is not configured; PostgreSQL integration was not run.";
    }
}

public class PostgreSqlResearchFactory : BrainSegFactory, IResearchTestDatabase
{
    private readonly string databaseName = $"brainseg_test_{Guid.NewGuid():N}";
    private readonly string connectionString;
    private readonly string administrativeConnection;
    private bool initialized;

    public PostgreSqlResearchFactory()
    {
        var configuration = new NpgsqlConnectionStringBuilder(Environment.GetEnvironmentVariable("BRAINSEG_TEST_POSTGRES")
            ?? throw new InvalidOperationException("A disposable PostgreSQL test server must be configured."));
        configuration.Database = "postgres";
        administrativeConnection = configuration.ConnectionString;
        configuration.Database = databaseName;
        configuration.IncludeErrorDetail = false;
        connectionString = configuration.ConnectionString;
    }

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        base.ConfigureWebHost(builder);
        builder.ConfigureAppConfiguration((_, configuration) => configuration.AddInMemoryCollection(
            new Dictionary<string, string?> { ["ConnectionStrings:Default"] = connectionString }));
    }

    public async Task InitializeAsync()
    {
        initialized = true;
        await RunAsync(async services =>
            await (await services.GetRequiredService<IDbContextProvider<BrainSegDbContext>>().GetDbContextAsync())
                .Database.MigrateAsync());
    }

    public async Task RunAsync(Func<IServiceProvider, Task> action)
    {
        using var scope = Services.CreateScope();
        using var unit = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>().Begin(requiresNew: true, isTransactional: false);
        await action(scope.ServiceProvider);
        await unit.CompleteAsync();
    }

    protected override void Dispose(bool disposing)
    {
        base.Dispose(disposing);
        if (!disposing || !initialized) return;
        using var connection = new NpgsqlConnection(administrativeConnection);
        connection.Open();
        using var command = new NpgsqlCommand($"DROP DATABASE IF EXISTS \"{databaseName}\" WITH (FORCE)", connection);
        command.ExecuteNonQuery();
    }
}

public class PostgreSqlPersistenceTests
{
    [PostgreSqlTheory]
    [InlineData("file-slice")]
    [InlineData("model-identity")]
    [InlineData("default-model")]
    [InlineData("idempotency")]
    [InlineData("result-job")]
    [InlineData("experiment")]
    [InlineData("foreign-key")]
    public async Task PostgreSQL_migration_and_native_constraints_are_enforced(string scenario)
    {
        using var factory = new PostgreSqlResearchFactory();
        await factory.InitializeAsync();
        await ResearchDatabaseAssertions.RejectDuplicateAsync(factory, scenario);
    }

    [PostgreSqlFact]
    public async Task PostgreSQL_detects_stale_concurrency_and_concurrent_scheduling_delete()
    {
        using var factory = new PostgreSqlResearchFactory();
        await factory.InitializeAsync();
        await ResearchDatabaseAssertions.RejectConcurrentUpdateAsync(factory);
    }

    [PostgreSqlFact]
    public async Task PostgreSQL_repository_converts_unique_violations_to_stable_business_errors()
    {
        using var factory = new PostgreSqlResearchFactory();
        await factory.InitializeAsync();
        await factory.RunAsync(async services => await services.GetRequiredService<IBrainStudyRepository>()
            .InsertAsync(AggregateTests.Study(), autoSave: true));
        var exception = await Assert.ThrowsAsync<BusinessException>(() => factory.RunAsync(async services =>
            await services.GetRequiredService<IBrainStudyRepository>().InsertAsync(AggregateTests.Study(), autoSave: true)));
        Assert.Equal(ResearchErrors.DuplicateStudy, exception.Code);
    }

    [PostgreSqlFact]
    public async Task PostgreSQL_scheduling_conflicts_with_a_stale_delete_snapshot()
    {
        using var factory = new PostgreSqlResearchFactory();
        await factory.InitializeAsync();
        await ResearchDatabaseAssertions.RejectConcurrentUpdateAsync(factory, deleteInstead: true);
    }
}
