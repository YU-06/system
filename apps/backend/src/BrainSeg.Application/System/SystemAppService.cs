using Microsoft.AspNetCore.Authorization;
using Volo.Abp.Application.Services;

namespace BrainSeg.System;

[AllowAnonymous]
public class SystemAppService : ApplicationService, ISystemAppService
{
    public Task<SystemStatusDto> GetAsync()
    {
        return Task.FromResult(new SystemStatusDto { ServerTimeUtc = Clock.Now });
    }
}
