using BrainSeg.Research;
using BrainSeg.Storage;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using System.Text.Json;
using Volo.Abp.EntityFrameworkCore;
using Volo.Abp.Uow;

namespace BrainSeg.Inference;

public sealed class InferenceJobWorker(IServiceScopeFactory scopeFactory, ILogger<InferenceJobWorker> logger)
    : BackgroundService
{
    private static readonly TimeSpan JobLease = TimeSpan.FromMinutes(5);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var claim = await ClaimNextAsync(stoppingToken);
                if (claim is null)
                {
                    await Task.Delay(TimeSpan.FromSeconds(1), stoppingToken);
                    continue;
                }

                using var scope = scopeFactory.CreateScope();
                var processor = scope.ServiceProvider.GetRequiredService<IInferenceJobProcessor>();
                try
                {
                    await processor.ExecuteAsync(claim.Value.JobId, claim.Value.ClaimToken, stoppingToken);
                }
                catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
                {
                    return;
                }
                catch (Exception exception)
                {
                    logger.LogError(exception, "Inference job failed for {JobId} with {ErrorCode}",
                        claim.Value.JobId, StableCode(exception));
                    await MarkFailedAsync(claim.Value.JobId, claim.Value.ClaimToken,
                        ToFailureReason(exception), stoppingToken);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
            catch (DbUpdateConcurrencyException)
            {
                await Task.Delay(TimeSpan.FromMilliseconds(100), stoppingToken);
            }
            catch (Exception exception)
            {
                logger.LogError(exception, "Inference queue polling failed with {ErrorCode}", StableCode(exception));
                await Task.Delay(TimeSpan.FromSeconds(2), stoppingToken);
            }
        }
    }

    private async Task<(Guid JobId, Guid ClaimToken)?> ClaimNextAsync(CancellationToken cancellationToken)
    {
        using var scope = scopeFactory.CreateScope();
        var units = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>();
        using var unit = units.Begin(requiresNew: true, isTransactional: true);
        var provider = scope.ServiceProvider.GetRequiredService<IDbContextProvider<BrainSegDbContext>>();
        var database = await provider.GetDbContextAsync();
        var now = DateTime.UtcNow;

        var expired = await database.SegmentationJobs
            .Where(job => job.Status == SegmentationJobStatus.Running
                && (job.LeaseExpiresAt != null && job.LeaseExpiresAt <= now
                    || job.LeaseExpiresAt == null && job.StartedTime <= now - JobLease))
            .OrderBy(job => job.LeaseExpiresAt ?? job.StartedTime)
            .Take(32)
            .ToListAsync(cancellationToken);
        foreach (var job in expired)
        {
            job.Fail(JobFailureReason.ExecutionFailed, now);
            if (job.RetryCount < SegmentationJob.MaxRetries) job.Retry(now);
        }
        await database.SaveChangesAsync(cancellationToken);

        var candidate = await database.SegmentationJobs
            .Where(job => job.Status == SegmentationJobStatus.Pending)
            .OrderBy(job => job.RequestedTime)
            .ThenBy(job => job.Id)
            .FirstOrDefaultAsync(cancellationToken);
        if (candidate is null)
        {
            await unit.CompleteAsync(cancellationToken);
            return null;
        }

        var claimToken = Guid.NewGuid();
        candidate.Start(now, now.Add(JobLease), claimToken);
        await database.SaveChangesAsync(cancellationToken);
        await unit.CompleteAsync(cancellationToken);
        return (candidate.Id, claimToken);
    }

    private async Task MarkFailedAsync(Guid jobId, Guid claimToken, JobFailureReason reason,
        CancellationToken cancellationToken)
    {
        using var scope = scopeFactory.CreateScope();
        var units = scope.ServiceProvider.GetRequiredService<IUnitOfWorkManager>();
        using var unit = units.Begin(requiresNew: true, isTransactional: true);
        var provider = scope.ServiceProvider.GetRequiredService<IDbContextProvider<BrainSegDbContext>>();
        var database = await provider.GetDbContextAsync();
        var job = await database.SegmentationJobs.SingleOrDefaultAsync(value => value.Id == jobId,
            cancellationToken);
        if (job is null || !job.IsClaimedBy(claimToken)) return;
        job.Fail(reason, DateTime.UtcNow);
        await database.SaveChangesAsync(cancellationToken);
        await unit.CompleteAsync(cancellationToken);
    }

    private static JobFailureReason ToFailureReason(Exception exception) => exception switch
    {
        InferenceClientException { Code: "INFERENCE_TIMEOUT" or "HTTP_408" or "HTTP_504" }
            => JobFailureReason.InferenceTimeout,
        InferenceClientException { Code: "MODEL_NOT_READY" or "HTTP_503" }
            => JobFailureReason.ModelNotReady,
        InferenceClientException { Code: "INVALID_FILE_TYPE" or "INVALID_NIFTI" or "INVALID_DIMENSIONS" }
            => JobFailureReason.InvalidInput,
        _ => JobFailureReason.ExecutionFailed
    };

    private static string StableCode(Exception exception) => exception switch
    {
        InferenceClientException clientException => clientException.Code,
        OperationCanceledException => "INFERENCE_TIMEOUT",
        _ => "EXECUTION_FAILED"
    };
}

public interface IInferenceJobProcessor
{
    Task ExecuteAsync(Guid jobId, Guid claimToken, CancellationToken cancellationToken);
}

public sealed class InferenceJobProcessor(IServiceScopeFactory scopeFactory, IObjectStorage storage,
    IObjectWriteIntentManager intents, IMlInferenceClient inferenceClient) : IInferenceJobProcessor
{
    public async Task ExecuteAsync(Guid jobId, Guid claimToken, CancellationToken cancellationToken)
    {
        var snapshot = await LoadSnapshotAsync(jobId, claimToken, cancellationToken);
        if (snapshot is null) return;

        var requestId = $"{jobId:N}-{snapshot.RetryCount}";
        var inferred = await inferenceClient.SegmentAsync(snapshot.InputObjectKey, snapshot.InputSha256,
            requestId, snapshot.CorrelationId, cancellationToken);
        ValidateResponse(snapshot, inferred);

        await using var remote = await inferenceClient.OpenPredictionAsync(inferred.PredictionObjectKey,
            snapshot.CorrelationId, cancellationToken);
        if (!string.Equals(remote.Sha256, inferred.PredictionSha256, StringComparison.OrdinalIgnoreCase))
            throw new InferenceClientException("PREDICTION_HASH_MISMATCH", false);
        var storedKey = $"{Guid.NewGuid():N}.bin";
        await intents.RegisterAsync(storedKey, "prediction-result", cancellationToken);
        var stored = await storage.SaveAsync(storedKey, remote.Content, cancellationToken);
        if (!string.Equals(stored.Sha256, inferred.PredictionSha256, StringComparison.OrdinalIgnoreCase))
            throw new InferenceClientException("PREDICTION_HASH_MISMATCH", false);

        var auxiliary = new StoredAuxiliaryArtifacts(
            await StoreArtifactAsync(inferred.ProbabilityArtifact, inferred.ProbabilitySha256,
                "probability", snapshot.CorrelationId, cancellationToken),
            await StoreArtifactAsync(inferred.BoundaryArtifact, inferred.BoundarySha256,
                "boundary", snapshot.CorrelationId, cancellationToken),
            await StoreArtifactAsync(inferred.UncertaintyArtifact, inferred.UncertaintySha256,
                "uncertainty", snapshot.CorrelationId, cancellationToken),
            await StoreArtifactAsync(inferred.ModelVarianceArtifact, inferred.ModelVarianceSha256,
                "model-variance", snapshot.CorrelationId, cancellationToken));

        await CompleteAsync(snapshot, claimToken, inferred, stored, auxiliary, cancellationToken);
    }

    private async Task<JobSnapshot?> LoadSnapshotAsync(Guid jobId, Guid claimToken,
        CancellationToken cancellationToken)
    {
        using var scope = scopeFactory.CreateScope();
        var provider = scope.ServiceProvider.GetRequiredService<IDbContextProvider<BrainSegDbContext>>();
        var database = await provider.GetDbContextAsync();
        var job = await database.SegmentationJobs.AsNoTracking()
            .SingleOrDefaultAsync(value => value.Id == jobId, cancellationToken);
        if (job is null || !job.IsClaimedBy(claimToken)) return null;
        var study = await database.BrainStudies.AsNoTracking()
            .SingleAsync(value => value.Id == job.StudyId, cancellationToken);
        var model = await database.ModelVersions.AsNoTracking()
            .SingleAsync(value => value.Id == job.ModelVersionId, cancellationToken);
        if (job.InputSha256 is null || job.Architecture is null || job.ModelSemanticVersion is null
            || job.PreprocessingVersion is null || job.WeightSha256 is null || job.InputSize is null
            || job.Threshold is null)
            throw new InferenceClientException("JOB_PROVENANCE_INCOMPLETE", false);
        if (study.OriginalFileSha256 != job.InputSha256 || model.Architecture != job.Architecture
            || model.SemanticVersion != job.ModelSemanticVersion || model.PreprocessingVersion != job.PreprocessingVersion
            || model.WeightSha256 != job.WeightSha256 || model.InputSize != job.InputSize
            || model.Threshold != job.Threshold)
            throw new InferenceClientException("JOB_PROVENANCE_MISMATCH", false);
        return new JobSnapshot(job.Id, job.RetryCount, job.CorrelationId, study.OriginalFileObjectKey,
            job.InputSha256, job.Architecture.Value, job.ModelSemanticVersion, job.PreprocessingVersion,
            job.WeightSha256, job.InputSize.Value, job.Threshold.Value);
    }

    private static void ValidateResponse(JobSnapshot job, InferenceSegmentResponse response)
    {
        if (response.ArtifactKind != "research")
            throw new InferenceClientException("TEST_ARTIFACT_NOT_ALLOWED", false);
        if (response.ModelVersion != job.ModelSemanticVersion
            || response.Architecture != job.Architecture.ToString()
            || response.PreprocessingVersion != job.PreprocessingVersion
            || response.InputSize != job.InputSize || response.Threshold != job.Threshold
            || !string.Equals(response.WeightSha256, job.WeightSha256, StringComparison.OrdinalIgnoreCase)
            || response.Space != "original" || response.MaskShape.Length != 3
            || response.MaskShape.Any(dimension => dimension < 1 || dimension > 512)
            || response.InputMode is not ("2d" or "2p5d")
            || response.ContextSlices is < 1 or > 9 || response.ContextSlices % 2 != 1
            || response.SliceFusion is not ("stack" or "center_attention")
            || (response.InputMode == "2d"
                && (response.ContextSlices != 1 || response.SliceFusion != "stack"))
            || response.EnsembleSize < 1
            || response.MemberWeightHashes is { } memberHashes
                && (memberHashes.Length != response.EnsembleSize
                    || memberHashes.Any(hash => hash.Length != 64 || !hash.All(Uri.IsHexDigit))
                    || !string.Equals(memberHashes[0], job.WeightSha256, StringComparison.OrdinalIgnoreCase))
            || (response.EnsembleSize > 1 && response.MemberWeightHashes is null)
            || !OptionalArtifactIsValid(response.ProbabilityArtifact, response.ProbabilitySha256)
            || !OptionalArtifactIsValid(response.BoundaryArtifact, response.BoundarySha256)
            || !OptionalArtifactIsValid(response.UncertaintyArtifact, response.UncertaintySha256)
            || !OptionalArtifactIsValid(response.ModelVarianceArtifact, response.ModelVarianceSha256)
            || response.BoundaryHead != (response.BoundaryArtifact is not null)
            || (response.UncertaintyArtifact is not null && response.UncertaintyMethod is null))
            throw new InferenceClientException("INFERENCE_RESPONSE_MISMATCH", false);
        if (response.MeanUncertainty is < 0 or > 100 || response.P95Uncertainty is < 0 or > 100)
            throw new InferenceClientException("INFERENCE_RESPONSE_MISMATCH", false);
    }

    private async Task CompleteAsync(JobSnapshot snapshot, Guid claimToken,
        InferenceSegmentResponse inference, StoredObject stored,
        StoredAuxiliaryArtifacts auxiliary, CancellationToken cancellationToken)
    {
        using var scope = scopeFactory.CreateScope();
        var services = scope.ServiceProvider;
        var unit = services.GetRequiredService<IUnitOfWorkManager>()
            .Begin(requiresNew: true, isTransactional: true);
        using (unit)
        {
            var provider = services.GetRequiredService<IDbContextProvider<BrainSegDbContext>>();
            var database = await provider.GetDbContextAsync();
            var job = await database.SegmentationJobs.SingleAsync(value => value.Id == snapshot.Id,
                cancellationToken);
            if (!job.IsClaimedBy(claimToken)) return;
            var result = new SegmentationResult(Guid.NewGuid(), job.Id, stored.ObjectKey, stored.Sha256,
                null, null, inference.TumorAreaPixels, inference.TumorAreaRatio,
                inference.Timings.InferenceMilliseconds, inference.Timings.PreprocessingMilliseconds,
                inference.Timings.PostprocessingMilliseconds, DateTime.UtcNow,
                remotePredictionObjectKey: inference.PredictionObjectKey,
                remotePredictionSha256: inference.PredictionSha256,
                probabilityObjectKey: auxiliary.Probability?.ObjectKey,
                probabilitySha256: auxiliary.Probability?.Sha256,
                boundaryObjectKey: auxiliary.Boundary?.ObjectKey,
                boundarySha256: auxiliary.Boundary?.Sha256,
                uncertaintyObjectKey: auxiliary.Uncertainty?.ObjectKey,
                uncertaintySha256: auxiliary.Uncertainty?.Sha256,
                modelVarianceObjectKey: auxiliary.ModelVariance?.ObjectKey,
                modelVarianceSha256: auxiliary.ModelVariance?.Sha256,
                inputMode: inference.InputMode,
                contextSlices: inference.ContextSlices,
                sliceFusion: inference.SliceFusion,
                boundaryHead: inference.BoundaryHead,
                deepSupervision: inference.DeepSupervision,
                memberWeightHashesJson: JsonSerializer.Serialize(
                    inference.MemberWeightHashes ?? [snapshot.WeightSha256]),
                ensembleSize: inference.EnsembleSize,
                uncertaintyMethod: inference.UncertaintyMethod,
                meanUncertainty: inference.MeanUncertainty,
                p95Uncertainty: inference.P95Uncertainty);
            job.Complete(DateTime.UtcNow);
            database.SegmentationResults.Add(result);
            var writeIntents = services.GetRequiredService<IObjectWriteIntentManager>();
            foreach (var objectKey in new string?[]
            {
                stored.ObjectKey,
                auxiliary.Probability?.ObjectKey,
                auxiliary.Boundary?.ObjectKey,
                auxiliary.Uncertainty?.ObjectKey,
                auxiliary.ModelVariance?.ObjectKey
            }.OfType<string>())
            {
                await writeIntents.CompleteInCurrentUnitOfWorkAsync(objectKey, cancellationToken);
            }
            await database.SaveChangesAsync(cancellationToken);
            await unit.CompleteAsync(cancellationToken);
        }
    }

    private sealed record JobSnapshot(Guid Id, int RetryCount, string CorrelationId, string InputObjectKey,
        string InputSha256, ModelArchitecture Architecture, string ModelSemanticVersion,
        string PreprocessingVersion, string WeightSha256, int InputSize, double Threshold);

    private async Task<StoredObject?> StoreArtifactAsync(string? objectKey, string? expectedSha256,
        string artifactType, string correlationId, CancellationToken cancellationToken)
    {
        if ((objectKey is null) != (expectedSha256 is null))
            throw new InferenceClientException("INFERENCE_RESPONSE_MISMATCH", false);
        if (objectKey is null) return null;

        await using var remote = await inferenceClient.OpenArtifactAsync(
            objectKey, correlationId, cancellationToken);
        if (!string.Equals(remote.Sha256, expectedSha256, StringComparison.OrdinalIgnoreCase))
            throw new InferenceClientException("ARTIFACT_HASH_MISMATCH", false);
        var storedKey = $"{Guid.NewGuid():N}.nii.gz";
        await intents.RegisterAsync(storedKey, $"prediction-{artifactType}", cancellationToken);
        var stored = await storage.SaveAsync(storedKey, remote.Content, cancellationToken);
        if (!string.Equals(stored.Sha256, expectedSha256, StringComparison.OrdinalIgnoreCase))
            throw new InferenceClientException("ARTIFACT_HASH_MISMATCH", false);
        return stored;
    }

    private static bool OptionalArtifactIsValid(string? objectKey, string? sha256) =>
        (objectKey is null && sha256 is null)
        || (objectKey is { Length: 39 }
            && objectKey.EndsWith(".nii.gz", StringComparison.Ordinal)
            && objectKey[..32].All(Uri.IsHexDigit)
            && sha256 is { Length: 64 }
            && sha256.All(Uri.IsHexDigit));

    private sealed record StoredAuxiliaryArtifacts(
        StoredObject? Probability,
        StoredObject? Boundary,
        StoredObject? Uncertainty,
        StoredObject? ModelVariance);
}
