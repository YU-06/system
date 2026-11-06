using Volo.Abp.Application.Services;

namespace BrainSeg.System;

public sealed class SystemStatusDto
{
    public string Service { get; set; } = "brainseg-backend";
    public string Status { get; set; } = "ok";
    public string Dataset { get; set; } = ResearchScope.Dataset;
    public string Modality { get; set; } = ResearchScope.Modality;
    public string Task { get; set; } = ResearchScope.Task;
    public string Disclaimer { get; set; } = ResearchScope.Disclaimer;
    public DateTime ServerTimeUtc { get; set; }
}

public interface ISystemAppService : IApplicationService
{
    Task<SystemStatusDto> GetAsync();
}
