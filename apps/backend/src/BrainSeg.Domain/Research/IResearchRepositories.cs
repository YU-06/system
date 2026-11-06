using Volo.Abp.Domain.Repositories;

namespace BrainSeg.Research;

public interface IBrainStudyRepository : IRepository<BrainStudy, Guid>;
public interface ISegmentationJobRepository : IRepository<SegmentationJob, Guid>;
public interface IModelVersionRepository : IRepository<ModelVersion, Guid>;
public interface ISegmentationResultRepository : IRepository<SegmentationResult, Guid>;
public interface IExperimentRunRepository : IRepository<ExperimentRun, Guid>;
