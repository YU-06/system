using Volo.Abp.Application.Dtos;
using Volo.Abp.Application.Services;

namespace BrainSeg.Research;

public interface IBrainStudyAppService : IApplicationService
{
    Task<BrainStudyDto> GetAsync(Guid id, CancellationToken cancellationToken = default);
    Task<PagedResultDto<BrainStudyDto>> GetListAsync(BrainStudyListInput input, CancellationToken cancellationToken = default);
    Task<BrainStudyDto> UploadAsync(UploadBrainStudyInput input, CancellationToken cancellationToken = default);
    Task<BrainStudyDto> UpdateAsync(Guid id, UpdateBrainStudyInput input, CancellationToken cancellationToken = default);
    Task<BrainStudyDto> ArchiveAsync(Guid id, ResearchCommandInput input, CancellationToken cancellationToken = default);
    Task DeleteAsync(Guid id, ResearchCommandInput input, CancellationToken cancellationToken = default);
}

public interface ISegmentationJobAppService : IApplicationService
{
    Task<SegmentationJobDto> GetAsync(Guid id, CancellationToken cancellationToken = default);
    Task<PagedResultDto<SegmentationJobDto>> GetListAsync(SegmentationJobListInput input, CancellationToken cancellationToken = default);
    Task<SegmentationJobDto> CreateAsync(CreateSegmentationJobInput input, CancellationToken cancellationToken = default);
    Task<SegmentationJobDto> StartAsync(Guid id, ResearchCommandInput input, CancellationToken cancellationToken = default);
    Task<SegmentationJobDto> ReportProgressAsync(Guid id, ReportJobProgressInput input, CancellationToken cancellationToken = default);
    Task<SegmentationJobDto> FailAsync(Guid id, FailSegmentationJobInput input, CancellationToken cancellationToken = default);
    Task<SegmentationJobDto> CancelAsync(Guid id, ResearchCommandInput input, CancellationToken cancellationToken = default);
    Task<SegmentationJobDto> RetryAsync(Guid id, ResearchCommandInput input, CancellationToken cancellationToken = default);
    Task<SegmentationResultDto> CompleteAsync(Guid id, CompleteSegmentationJobInput input, CancellationToken cancellationToken = default);
}

public interface IModelVersionAppService : IApplicationService
{
    Task<ModelVersionDto> GetAsync(Guid id, CancellationToken cancellationToken = default);
    Task<PagedResultDto<ModelVersionDto>> GetListAsync(ModelVersionListInput input, CancellationToken cancellationToken = default);
    Task<ModelVersionDto> CreateAsync(CreateModelVersionInput input, CancellationToken cancellationToken = default);
    Task<ModelVersionDto> SetStateAsync(Guid id, ChangeModelStateInput input, CancellationToken cancellationToken = default);
}

public interface ISegmentationResultAppService : IApplicationService
{
    Task<SegmentationResultDto> GetAsync(Guid id, CancellationToken cancellationToken = default);
    Task<PagedResultDto<SegmentationResultDto>> GetListAsync(SegmentationResultListInput input, CancellationToken cancellationToken = default);
}

public interface IExperimentRunAppService : IApplicationService
{
    Task<ExperimentRunDto> GetAsync(Guid id, CancellationToken cancellationToken = default);
    Task<PagedResultDto<ExperimentRunDto>> GetListAsync(ExperimentRunListInput input, CancellationToken cancellationToken = default);
    Task<ExperimentRunDto> CreateAsync(CreateExperimentRunInput input, CancellationToken cancellationToken = default);
}
