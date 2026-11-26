using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Volo.Abp.EntityFrameworkCore;
using Volo.Abp.Uow;

namespace BrainSeg.Storage;

public sealed class ObjectWriteIntentManager(IServiceScopeFactory scopeFactory,
    IDbContextProvider<BrainSegDbContext> contextProvider) : IObjectWriteIntentManager
{
    public async Task RegisterAsync(string objectKey, string purpose, CancellationToken cancellationToken)
    {
        using var scope = scopeFactory.CreateScope();
        using var unit = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>()
            .Begin(requiresNew: true, isTransactional: true);
        var database = await scope.ServiceProvider.GetRequiredService<IDbContextProvider<BrainSegDbContext>>()
            .GetDbContextAsync();
        database.ObjectWriteIntents.Add(new ObjectWriteIntent(Guid.NewGuid(), objectKey, purpose, DateTime.UtcNow));
        await database.SaveChangesAsync(cancellationToken);
        await unit.CompleteAsync(cancellationToken);
    }

    public async Task CompleteInCurrentUnitOfWorkAsync(string objectKey, CancellationToken cancellationToken)
    {
        var database = await contextProvider.GetDbContextAsync();
        var intent = await database.ObjectWriteIntents.SingleOrDefaultAsync(
            value => value.ObjectKey == objectKey, cancellationToken);
        if (intent is null) return;
        database.ObjectWriteIntents.Remove(intent);
        await database.SaveChangesAsync(cancellationToken);
    }
}

public sealed class ObjectWriteIntentWorker(IServiceScopeFactory scopeFactory, IObjectStorage storage,
    ILogger<ObjectWriteIntentWorker> logger) : BackgroundService
{
    private static readonly TimeSpan GracePeriod = TimeSpan.FromMinutes(5);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await ProcessBatchAsync(stoppingToken);
                await Task.Delay(TimeSpan.FromSeconds(15), stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception exception)
            {
                logger.LogError(exception, "Object compensation scan failed");
                await Task.Delay(TimeSpan.FromSeconds(30), stoppingToken);
            }
        }
    }

    private async Task ProcessBatchAsync(CancellationToken cancellationToken)
    {
        using var scope = scopeFactory.CreateScope();
        var services = scope.ServiceProvider;
        using var unit = services.GetRequiredService<IUnitOfWorkManager>()
            .Begin(requiresNew: true, isTransactional: true);
        var database = await services.GetRequiredService<IDbContextProvider<BrainSegDbContext>>()
            .GetDbContextAsync();
        var now = DateTime.UtcNow;
        var intents = await database.ObjectWriteIntents
            .Where(value => value.RequestedTime <= now - GracePeriod && value.NextAttemptTime <= now)
            .OrderBy(value => value.NextAttemptTime)
            .Take(32)
            .ToListAsync(cancellationToken);

        foreach (var intent in intents)
        {
            var isReferenced = await database.BrainStudies.AnyAsync(
                    value => value.OriginalFileObjectKey == intent.ObjectKey
                        || value.GroundTruthObjectKey == intent.ObjectKey, cancellationToken)
                || await database.SegmentationResults.AnyAsync(
                    value => value.MaskObjectKey == intent.ObjectKey
                        || value.OverlayObjectKey == intent.ObjectKey
                        || value.ContourObjectKey == intent.ObjectKey, cancellationToken);
            if (isReferenced)
            {
                database.ObjectWriteIntents.Remove(intent);
                continue;
            }

            try
            {
                await storage.DeleteAsync(intent.ObjectKey, cancellationToken);
                database.ObjectWriteIntents.Remove(intent);
            }
            catch (Exception exception) when (exception is not OperationCanceledException)
            {
                intent.DelayNextAttempt(now);
                logger.LogWarning(exception, "Object compensation will retry for {ObjectKey}; attempt {AttemptCount}",
                    intent.ObjectKey, intent.AttemptCount);
            }
        }

        await database.SaveChangesAsync(cancellationToken);
        await unit.CompleteAsync(cancellationToken);
    }
}
