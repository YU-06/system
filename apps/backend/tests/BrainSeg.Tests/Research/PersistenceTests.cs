using BrainSeg.Research;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Volo.Abp.Data;
using Volo.Abp.Domain.Repositories;
using Volo.Abp.EntityFrameworkCore;
using Volo.Abp.Uow;
using Xunit;

namespace BrainSeg.Tests.Research;

public class PersistenceTests
{
    [Theory]
    [InlineData("file-slice")]
    [InlineData("model-identity")]
    [InlineData("default-model")]
    [InlineData("idempotency")]
    [InlineData("result-job")]
    [InlineData("experiment")]
    [InlineData("foreign-key")]
    public async Task Database_rejects_duplicate_identities_and_invalid_foreign_keys(string scenario)
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        await ResearchDatabaseAssertions.RejectDuplicateAsync(factory, scenario);
    }

    [Fact]
    public async Task Two_loaded_versions_conflict_at_the_database_not_only_in_dto_validation()
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        await ResearchDatabaseAssertions.RejectConcurrentUpdateAsync(factory);
    }

    [Fact]
    public async Task Scheduling_a_job_invalidates_a_concurrent_soft_delete_snapshot()
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        await ResearchDatabaseAssertions.RejectConcurrentUpdateAsync(factory, deleteInstead: true);
    }

    [Fact]
    public async Task Soft_deletion_preserves_rows_and_releases_only_active_study_identities()
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        var study = AggregateTests.Study();
        await factory.RunAsync(async services => await services.GetRequiredService<IBrainStudyRepository>().InsertAsync(study, autoSave: true));
        await factory.RunAsync(async services => await services.GetRequiredService<IBrainStudyRepository>().DeleteAsync(study.Id, autoSave: true));
        await factory.RunAsync(async services =>
        {
            var repository = services.GetRequiredService<IBrainStudyRepository>();
            Assert.Equal(0, await repository.GetCountAsync());
            await repository.InsertAsync(AggregateTests.Study(), autoSave: true);
            using (services.GetRequiredService<IDataFilter>().Disable<Volo.Abp.ISoftDelete>())
                Assert.Equal(2, await repository.GetCountAsync());
        });
    }

    [Fact]
    public async Task Unique_study_numbers_are_enforced_by_a_real_relational_database()
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        await factory.RunAsync(async services =>
            await services.GetRequiredService<IBrainStudyRepository>().InsertAsync(AggregateTests.Study(), autoSave: true));
        await Assert.ThrowsAsync<DbUpdateException>(() => factory.RunAsync(async services =>
            await services.GetRequiredService<IBrainStudyRepository>().InsertAsync(
                new BrainStudy(Guid.NewGuid(), "study-001", "case-002", AggregateTests.ObjectKey(), new string('b', 64), 240, 240, 0), autoSave: true)));
    }

    [Fact]
    public async Task Model_maps_foreign_keys_partial_indexes_and_concurrency_tokens()
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        await factory.RunAsync(async services =>
        {
            var context = await services.GetRequiredService<IDbContextProvider<BrainSegDbContext>>().GetDbContextAsync();
            foreach (var type in new[] { typeof(BrainStudy), typeof(SegmentationJob), typeof(ModelVersion), typeof(SegmentationResult), typeof(ExperimentRun) })
            {
                var entity = context.Model.FindEntityType(type)!;
                Assert.True(entity.FindProperty("ConcurrencyStamp")!.IsConcurrencyToken);
            }
            var job = context.Model.FindEntityType(typeof(SegmentationJob))!;
            Assert.Equal(2, job.GetForeignKeys().Count());
            Assert.All(job.GetForeignKeys(), key => Assert.Equal(DeleteBehavior.Restrict, key.DeleteBehavior));
            Assert.Contains(context.Model.FindEntityType(typeof(BrainStudy))!.GetIndexes(),
                index => index.IsUnique && index.GetFilter() == "\"IsDeleted\" = false");
        });
    }
}

internal static class ResearchDatabaseAssertions
{
    public static async Task RejectDuplicateAsync(IResearchTestDatabase factory, string scenario)
    {
        var study = AggregateTests.Study();
        study.MarkReady();
        var model = AggregateTests.Model();
        model.Activate(AggregateTests.Now);
        if (scenario == "default-model") model.MakeDefault();
        var job = new SegmentationJob(Guid.NewGuid(), study.Id, model.Id, ResearchFactory.UserId,
            "same-key", "database-check", AggregateTests.Now);
        if (scenario == "result-job")
        {
            job.Start(AggregateTests.Now);
            job.Complete(AggregateTests.Now);
        }
        await factory.RunAsync(async services =>
        {
            var database = await ContextAsync(services);
            database.AddRange(study, model, job);
            if (scenario == "result-job") database.Add(Result(job.Id));
            if (scenario == "experiment") database.Add(Experiment(model.Id));
            await database.SaveChangesAsync();
        });
        await Assert.ThrowsAsync<DbUpdateException>(() => factory.RunAsync(async services =>
        {
            var database = await ContextAsync(services);
            object duplicate = scenario switch
            {
                "file-slice" => new BrainStudy(Guid.NewGuid(), "other-study", "case-002", AggregateTests.ObjectKey(), AggregateTests.Hash, 240, 240, 0),
                "model-identity" => AggregateTests.Model("BASELINE"),
                "default-model" => DefaultModel(),
                "idempotency" => new SegmentationJob(Guid.NewGuid(), study.Id, model.Id, ResearchFactory.UserId, "same-key", "database-check-2", AggregateTests.Now),
                "result-job" => Result(job.Id),
                "experiment" => Experiment(model.Id),
                _ => new SegmentationJob(Guid.NewGuid(), Guid.NewGuid(), model.Id, ResearchFactory.UserId, "missing-parent", "foreign-key-check", AggregateTests.Now)
            };
            database.Add(duplicate);
            await database.SaveChangesAsync();
        }));
    }

    public static async Task RejectConcurrentUpdateAsync(IResearchTestDatabase factory, bool deleteInstead = false)
    {
        var study = AggregateTests.Study();
        study.MarkReady();
        await factory.RunAsync(async services => await services.GetRequiredService<IBrainStudyRepository>().InsertAsync(study, autoSave: true));
        using var firstScope = factory.Services.CreateScope();
        using var firstUnit = firstScope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>().Begin(requiresNew: true, isTransactional: false);
        var firstDatabase = await ContextAsync(firstScope.ServiceProvider);
        var first = await firstDatabase.BrainStudies.SingleAsync(value => value.Id == study.Id);
        using var secondScope = factory.Services.CreateScope();
        using var secondUnit = secondScope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>().Begin(requiresNew: true, isTransactional: false);
        var secondDatabase = await ContextAsync(secondScope.ServiceProvider);
        var second = await secondDatabase.BrainStudies.SingleAsync(value => value.Id == study.Id);
        if (deleteInstead) first.RecordJobRequest();
        else first.ChangePseudonym("first-version");
        await firstDatabase.SaveChangesAsync();
        if (deleteInstead)
        {
            second.EnsureCanDelete(false);
            secondDatabase.Remove(second);
        }
        else second.ChangePseudonym("stale-version");
        await Assert.ThrowsAsync<AbpDbConcurrencyException>(() => secondDatabase.SaveChangesAsync());
    }

    private static Task<BrainSegDbContext> ContextAsync(IServiceProvider services) =>
        services.GetRequiredService<IDbContextProvider<BrainSegDbContext>>().GetDbContextAsync();

    private static ModelVersion DefaultModel()
    {
        var model = AggregateTests.Model("other-model");
        model.Activate(AggregateTests.Now);
        model.MakeDefault();
        return model;
    }

    private static SegmentationResult Result(Guid jobId) => new(Guid.NewGuid(), jobId, AggregateTests.ObjectKey(),
        AggregateTests.ObjectKey(), AggregateTests.ObjectKey(), 0, 0, 0, 0, AggregateTests.Now);

    private static ExperimentRun Experiment(Guid modelId) => new(Guid.NewGuid(), "repro-fixture", AggregateTests.Hash,
        new string('b', 40), AggregateTests.Hash, 42, modelId, "{\"status\":\"NotRun\"}", AggregateTests.ObjectKey(), AggregateTests.Now);
}
