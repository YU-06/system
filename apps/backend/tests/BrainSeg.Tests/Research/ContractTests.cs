using System.Globalization;
using BrainSeg.Research;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Localization;
using Volo.Abp.Authorization.Permissions;
using Volo.Abp.ObjectMapping;
using Xunit;

namespace BrainSeg.Tests.Research;

public class ContractTests
{
    [Fact]
    public async Task Permission_definitions_and_chinese_resources_are_discovered()
    {
        using var factory = new BrainSegFactory();
        using var scope = factory.Services.CreateScope();
        var manager = scope.ServiceProvider.GetRequiredService<IPermissionDefinitionManager>();
        Assert.NotNull(await manager.GetAsync(ResearchPermissions.BrainStudies.Delete));
        Assert.NotNull(await manager.GetAsync(ResearchPermissions.SegmentationJobs.Execute));
        Assert.NotNull(await manager.GetAsync(ResearchPermissions.ModelVersions.Manage));
        var previous = CultureInfo.CurrentUICulture;
        try
        {
            CultureInfo.CurrentUICulture = CultureInfo.GetCultureInfo("zh-Hans");
            var localizer = scope.ServiceProvider.GetRequiredService<IStringLocalizer<BrainSegResource>>();
            Assert.Contains("幂等", localizer[ResearchErrors.IdempotencyConflict].Value);
        }
        finally
        {
            CultureInfo.CurrentUICulture = previous;
        }
    }

    [Fact]
    public void AutoMapper_projects_only_dtos_without_file_bytes()
    {
        using var factory = new BrainSegFactory();
        using var scope = factory.Services.CreateScope();
        var mapper = scope.ServiceProvider.GetRequiredService<IObjectMapper>();
        var study = AggregateTests.Study();
        var dto = mapper.Map<BrainStudy, BrainStudyDto>(study);
        Assert.Equal(study.OriginalFileSha256, dto.OriginalFileSha256);
        Assert.Equal(study.ConcurrencyStamp, dto.ConcurrencyStamp);
        Assert.DoesNotContain(typeof(BrainStudyDto).GetProperties(), property => property.PropertyType == typeof(byte[]));
        var job = JobStateTests.CreateJob();
        Assert.Equal(TimeSpan.Zero, mapper.Map<SegmentationJob, SegmentationJobDto>(job).RequestedTime.Offset);
    }
}
