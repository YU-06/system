using AutoMapper;

namespace BrainSeg.Research;

public class ResearchAutoMapperProfile : Profile
{
    public ResearchAutoMapperProfile()
    {
        CreateMap<BrainStudy, BrainStudyDto>();
        CreateMap<SegmentationJob, SegmentationJobDto>()
            .ForMember(destination => destination.RequestedTime, options => options.MapFrom(source => Utc(source.RequestedTime)))
            .ForMember(destination => destination.StartedTime, options => options.MapFrom(source => OptionalUtc(source.StartedTime)))
            .ForMember(destination => destination.CompletedTime, options => options.MapFrom(source => OptionalUtc(source.CompletedTime)));
        CreateMap<ModelVersion, ModelVersionDto>()
            .ForMember(destination => destination.PublishedTime, options => options.MapFrom(source => OptionalUtc(source.PublishedTime)));
        CreateMap<SegmentationResult, SegmentationResultDto>()
            .ForMember(destination => destination.CreatedTime, options => options.MapFrom(source => Utc(source.CreatedTime)));
        CreateMap<ExperimentRun, ExperimentRunDto>()
            .ForMember(destination => destination.CreatedTime, options => options.MapFrom(source => Utc(source.CreatedTime)));
    }

    private static DateTimeOffset Utc(DateTime value) => new(DateTime.SpecifyKind(value, DateTimeKind.Utc));
    private static DateTimeOffset? OptionalUtc(DateTime? value) => value.HasValue ? Utc(value.Value) : null;
}
