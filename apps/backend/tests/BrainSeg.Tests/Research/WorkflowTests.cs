using System.Net;
using System.Net.Http.Json;
using BrainSeg.Research;
using BrainSeg.Storage;
using Microsoft.Extensions.DependencyInjection;
using Volo.Abp.Domain.Repositories;
using Xunit;

namespace BrainSeg.Tests.Research;

public class WorkflowTests
{
    private static string[] Permissions => typeof(ResearchPermissions).GetNestedTypes()
        .SelectMany(type => type.GetFields()).Select(permissionField => (string)permissionField.GetRawConstantValue()!).ToArray();

    private static async Task<T> PostAsync<T>(HttpClient client, string path, object input)
    {
        using var response = await client.PostAsJsonAsync(path, input);
        Assert.True(response.IsSuccessStatusCode, await response.Content.ReadAsStringAsync());
        return (await response.Content.ReadFromJsonAsync<T>())!;
    }

    internal static async Task<(BrainStudy Study, ModelVersion Model, string Artifact)> SeedAsync(ResearchFactory factory)
    {
        BrainStudy study = null!;
        ModelVersion model = null!;
        var artifact = string.Empty;
        await factory.RunAsync(async services =>
        {
            using var fixture = new MemoryStream("synthetic-artifact-not-a-trained-model"u8.ToArray());
            var stored = await services.GetRequiredService<IObjectStorage>().SaveAsync(fixture);
            artifact = stored.ObjectKey;
            study = AggregateTests.Study();
            study.MarkReady();
            model = new ModelVersion(Guid.NewGuid(), "workflow-baseline", ModelArchitecture.UNet, "1.0.0",
                stored.ObjectKey, stored.Sha256, 0.5, "{\"status\":\"NotRun\"}");
            model.Activate(AggregateTests.Now);
            await services.GetRequiredService<IBrainStudyRepository>().InsertAsync(study, autoSave: true);
            await services.GetRequiredService<IModelVersionRepository>().InsertAsync(model, autoSave: true);
        });
        return (study, model, artifact);
    }

    [Fact]
    public async Task Idempotent_jobs_complete_once_and_soft_deleted_studies_retain_results()
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        var seed = await SeedAsync(factory);
        using var client = factory.AuthenticatedClient(Permissions);
        var input = new CreateSegmentationJobInput { StudyId = seed.Study.Id, ModelVersionId = seed.Model.Id, IdempotencyKey = "workflow-key" };
        var job = await PostAsync<SegmentationJobDto>(client, "/api/app/segmentation-job", input);
        var repeated = await PostAsync<SegmentationJobDto>(client, "/api/app/segmentation-job", input);
        Assert.Equal(job.Id, repeated.Id);
        var study = (await client.GetFromJsonAsync<BrainStudyDto>($"/api/app/brain-study/{seed.Study.Id}"))!;
        Assert.Equal(1, study.JobRequestCount);
        using var blockedDelete = new HttpRequestMessage(HttpMethod.Delete,
            $"/api/app/brain-study/{study.Id}?concurrencyStamp={Uri.EscapeDataString(study.ConcurrencyStamp)}");
        using var blocked = await client.SendAsync(blockedDelete);
        Assert.Equal(HttpStatusCode.Conflict, blocked.StatusCode);
        Assert.Contains(ResearchErrors.StudyHasActiveJobs, await blocked.Content.ReadAsStringAsync());
        job = await PostAsync<SegmentationJobDto>(client, $"/api/app/segmentation-job/{job.Id}/start",
            new ResearchCommandInput { ConcurrencyStamp = job.ConcurrencyStamp });
        var result = await PostAsync<SegmentationResultDto>(client, $"/api/app/segmentation-job/{job.Id}/complete",
            new CompleteSegmentationJobInput
            {
                ConcurrencyStamp = job.ConcurrencyStamp,
                MaskObjectKey = seed.Artifact,
                OverlayObjectKey = seed.Artifact,
                ContourObjectKey = seed.Artifact,
                TumorAreaPixels = 3,
                InferenceMilliseconds = 1
            });
        Assert.Null(result.Dice);
        using var deletion = new HttpRequestMessage(HttpMethod.Delete,
            $"/api/app/brain-study/{study.Id}?concurrencyStamp={Uri.EscapeDataString(study.ConcurrencyStamp)}");
        using var deleted = await client.SendAsync(deletion);
        Assert.Equal(HttpStatusCode.NoContent, deleted.StatusCode);
        using var hidden = await client.GetAsync($"/api/app/brain-study/{study.Id}");
        Assert.Equal(HttpStatusCode.NotFound, hidden.StatusCode);
        Assert.NotNull(await client.GetFromJsonAsync<SegmentationResultDto>($"/api/app/segmentation-result/{result.Id}"));
        var completed = (await client.GetFromJsonAsync<SegmentationJobDto>($"/api/app/segmentation-job/{job.Id}"))!;
        Assert.Equal(SegmentationJobStatus.Succeeded, completed.Status);
        Assert.Equal(100, completed.Progress);
        await factory.RunAsync(async services =>
        {
            await using var artifact = await services.GetRequiredService<IObjectStorage>().OpenReadAsync(seed.Artifact);
            Assert.True(artifact.Length > 0);
        });
    }

    [Fact]
    public async Task Model_registration_activation_and_experiment_records_use_actual_object_hashes()
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        var seed = await SeedAsync(factory);
        using var client = factory.AuthenticatedClient(Permissions);
        var model = await PostAsync<ModelVersionDto>(client, "/api/app/model-version", new CreateModelVersionInput
        {
            Name = "attention-baseline",
            Architecture = ModelArchitecture.AttentionUNet,
            SemanticVersion = "1.0.0",
            WeightObjectKey = seed.Artifact,
            WeightSha256 = seed.Model.WeightSha256
        });
        model = await PostAsync<ModelVersionDto>(client, $"/api/app/model-version/{model.Id}/set-state",
            new ChangeModelStateInput { ConcurrencyStamp = model.ConcurrencyStamp, IsActive = true, IsDefault = true });
        Assert.True(model.IsDefault);
        var experiment = await PostAsync<ExperimentRunDto>(client, "/api/app/experiment-run", new CreateExperimentRunInput
        {
            ExperimentName = "synthetic-contract-fixture",
            ConfigHash = AggregateTests.Hash,
            DatasetSplitHash = AggregateTests.Hash,
            GitCommit = new string('b', 40),
            ModelVersionId = model.Id,
            RandomSeed = 42,
            ArtifactObjectKey = seed.Artifact
        });
        Assert.Contains("NotRun", experiment.MetricsJson);
        var listed = await client.GetFromJsonAsync<Volo.Abp.Application.Dtos.PagedResultDto<ExperimentRunDto>>(
            $"/api/app/experiment-run?modelVersionId={model.Id}&randomSeed=42&sorting=randomSeed%20asc");
        Assert.Equal(experiment.Id, Assert.Single(listed!.Items).Id);
    }

    [Fact]
    public async Task Failed_completion_does_not_persist_success_or_partial_results()
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        var seed = await SeedAsync(factory);
        using var client = factory.AuthenticatedClient(Permissions);
        var job = await PostAsync<SegmentationJobDto>(client, "/api/app/segmentation-job", new CreateSegmentationJobInput
        { StudyId = seed.Study.Id, ModelVersionId = seed.Model.Id, IdempotencyKey = "atomic-completion" });
        using var premature = await client.PostAsJsonAsync($"/api/app/segmentation-job/{job.Id}/complete",
            new CompleteSegmentationJobInput
            {
                ConcurrencyStamp = job.ConcurrencyStamp,
                MaskObjectKey = seed.Artifact,
                OverlayObjectKey = seed.Artifact,
                ContourObjectKey = seed.Artifact
            });
        Assert.Equal(HttpStatusCode.Conflict, premature.StatusCode);
        job = await PostAsync<SegmentationJobDto>(client, $"/api/app/segmentation-job/{job.Id}/start",
            new ResearchCommandInput { ConcurrencyStamp = job.ConcurrencyStamp });
        using var missing = await client.PostAsJsonAsync($"/api/app/segmentation-job/{job.Id}/complete",
            new CompleteSegmentationJobInput
            {
                ConcurrencyStamp = job.ConcurrencyStamp,
                MaskObjectKey = AggregateTests.ObjectKey(),
                OverlayObjectKey = seed.Artifact,
                ContourObjectKey = seed.Artifact
            });
        Assert.Equal(HttpStatusCode.NotFound, missing.StatusCode);
        var unchanged = (await client.GetFromJsonAsync<SegmentationJobDto>($"/api/app/segmentation-job/{job.Id}"))!;
        Assert.Equal(SegmentationJobStatus.Running, unchanged.Status);
        Assert.Null(unchanged.CompletedTime);
        Assert.Equal(job.ConcurrencyStamp, unchanged.ConcurrencyStamp);
        await factory.RunAsync(async services => Assert.Equal(0,
            await services.GetRequiredService<ISegmentationResultRepository>().GetCountAsync()));
        using var changedIdentity = await client.PostAsJsonAsync("/api/app/segmentation-job", new CreateSegmentationJobInput
        { StudyId = Guid.NewGuid(), ModelVersionId = seed.Model.Id, IdempotencyKey = "atomic-completion" });
        Assert.Equal(HttpStatusCode.Conflict, changedIdentity.StatusCode);
        Assert.Contains(ResearchErrors.IdempotencyConflict, await changedIdentity.Content.ReadAsStringAsync());
    }
}
