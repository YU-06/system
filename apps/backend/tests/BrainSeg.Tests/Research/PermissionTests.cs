using System.Net;
using System.Net.Http.Json;
using BrainSeg.Research;
using Xunit;

namespace BrainSeg.Tests.Research;

public class PermissionTests
{
    [Theory]
    [InlineData("job-create")]
    [InlineData("job-start")]
    [InlineData("job-progress")]
    [InlineData("job-fail")]
    [InlineData("job-cancel")]
    [InlineData("job-retry")]
    [InlineData("job-complete")]
    [InlineData("model-create")]
    [InlineData("model-state")]
    [InlineData("experiment-create")]
    public async Task Read_permissions_do_not_authorize_mutating_commands(string scenario)
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        using var client = factory.AuthenticatedClient(ResearchPermissions.BrainStudies.Default,
            ResearchPermissions.SegmentationJobs.Default, ResearchPermissions.ModelVersions.Default,
            ResearchPermissions.SegmentationResults.Default, ResearchPermissions.ExperimentRuns.Default);
        var id = Guid.NewGuid();
        var stamp = Guid.NewGuid().ToString("N");
        var command = new ResearchCommandInput { ConcurrencyStamp = stamp };
        var (path, body) = scenario switch
        {
            "job-create" => ("/api/app/segmentation-job", (object)new CreateSegmentationJobInput
            { StudyId = id, ModelVersionId = id, IdempotencyKey = "permission-test" }),
            "job-progress" => ($"/api/app/segmentation-job/{id}/report-progress", new ReportJobProgressInput { ConcurrencyStamp = stamp, Progress = 10 }),
            "job-fail" => ($"/api/app/segmentation-job/{id}/fail", new FailSegmentationJobInput { ConcurrencyStamp = stamp }),
            "job-complete" => ($"/api/app/segmentation-job/{id}/complete", new CompleteSegmentationJobInput
            { ConcurrencyStamp = stamp, MaskObjectKey = "mask.bin", OverlayObjectKey = "overlay.bin", ContourObjectKey = "contour.bin" }),
            "model-create" => ("/api/app/model-version", new CreateModelVersionInput
            { Name = "permission-test", SemanticVersion = "1.0.0", WeightObjectKey = "weights.bin", WeightSha256 = AggregateTests.Hash }),
            "model-state" => ($"/api/app/model-version/{id}/set-state", new ChangeModelStateInput { ConcurrencyStamp = stamp, IsActive = true }),
            "experiment-create" => ("/api/app/experiment-run", new CreateExperimentRunInput
            {
                ExperimentName = "permission-test",
                ConfigHash = AggregateTests.Hash,
                DatasetSplitHash = AggregateTests.Hash,
                GitCommit = new string('b', 40),
                ModelVersionId = id,
                ArtifactObjectKey = "experiment.bin"
            }),
            _ => ($"/api/app/segmentation-job/{id}/{scenario[4..]}", (object)command)
        };
        using var response = await client.PostAsJsonAsync(path, body);
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public void Assemblies_preserve_domain_and_contract_dependency_boundaries()
    {
        var domain = typeof(BrainStudy).Assembly.GetReferencedAssemblies().Select(assembly => assembly.Name).ToArray();
        Assert.DoesNotContain("BrainSeg.Application", domain);
        Assert.DoesNotContain("BrainSeg.EntityFrameworkCore", domain);
        Assert.DoesNotContain("BrainSeg.Application.Contracts", domain);
        var contracts = typeof(BrainStudyDto).Assembly.GetReferencedAssemblies().Select(assembly => assembly.Name).ToArray();
        Assert.DoesNotContain("BrainSeg.Domain", contracts);
        Assert.DoesNotContain("BrainSeg.EntityFrameworkCore", contracts);
        Assert.DoesNotContain("BrainSeg.EntityFrameworkCore", typeof(BrainSegApplicationModule).Assembly.GetReferencedAssemblies().Select(assembly => assembly.Name));
    }
}
