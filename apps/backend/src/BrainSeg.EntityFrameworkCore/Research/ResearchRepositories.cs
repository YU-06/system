using Microsoft.EntityFrameworkCore;
using Npgsql;
using Volo.Abp;
using Volo.Abp.Domain.Entities;
using Volo.Abp.Domain.Repositories.EntityFrameworkCore;
using Volo.Abp.EntityFrameworkCore;

namespace BrainSeg.Research;

public class EfCoreBrainStudyRepository(IDbContextProvider<BrainSegDbContext> provider)
    : ResearchRepository<BrainStudy>(provider), IBrainStudyRepository;

public class EfCoreSegmentationJobRepository(IDbContextProvider<BrainSegDbContext> provider)
    : ResearchRepository<SegmentationJob>(provider), ISegmentationJobRepository;

public class EfCoreModelVersionRepository(IDbContextProvider<BrainSegDbContext> provider)
    : ResearchRepository<ModelVersion>(provider), IModelVersionRepository;

public class EfCoreSegmentationResultRepository(IDbContextProvider<BrainSegDbContext> provider)
    : ResearchRepository<SegmentationResult>(provider), ISegmentationResultRepository;

public class EfCoreExperimentRunRepository(IDbContextProvider<BrainSegDbContext> provider)
    : ResearchRepository<ExperimentRun>(provider), IExperimentRunRepository;

public abstract class ResearchRepository<TEntity>(IDbContextProvider<BrainSegDbContext> provider)
    : EfCoreRepository<BrainSegDbContext, TEntity, Guid>(provider) where TEntity : class, IEntity<Guid>
{
    public override Task<TEntity> InsertAsync(TEntity entity, bool autoSave = false, CancellationToken cancellationToken = default) =>
        WriteAsync(() => base.InsertAsync(entity, autoSave, cancellationToken));

    public override Task<TEntity> UpdateAsync(TEntity entity, bool autoSave = false, CancellationToken cancellationToken = default) =>
        WriteAsync(() => base.UpdateAsync(entity, autoSave, cancellationToken));

    private static async Task<TEntity> WriteAsync(Func<Task<TEntity>> write)
    {
        try
        {
            return await write();
        }
        catch (DbUpdateException exception) when (exception.InnerException is PostgresException { SqlState: PostgresErrorCodes.UniqueViolation })
        {
            var code = ((PostgresException)exception.InnerException).ConstraintName switch
            {
                "UX_BrainStudies_Number" or "UX_BrainStudies_FileSlice" => ResearchErrors.DuplicateStudy,
                "UX_ModelVersions_Identity" => ResearchErrors.DuplicateModelVersion,
                "UX_ModelVersions_Default" => ResearchErrors.DefaultModelConflict,
                "UX_SegmentationJobs_Idempotency" => ResearchErrors.IdempotencyConflict,
                "UX_SegmentationResults_Job" => ResearchErrors.ResultAlreadyExists,
                "UX_ExperimentRuns_Reproducibility" => ResearchErrors.DuplicateExperiment,
                _ => ResearchErrors.InvalidInput
            };
            throw new BusinessException(code, innerException: exception);
        }
    }
}
