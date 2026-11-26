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
    public async Task Jobs_are_idempotent_worker_completed_and_retained_after_study_deletion()
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
        var activeJob = await PostAsync<SegmentationJobDto>(client, "/api/app/segmentation-job",
            new CreateSegmentationJobInput
            {
                StudyId = seed.Study.Id,
                ModelVersionId = seed.Model.Id,
                IdempotencyKey = "workflow-active-key"
            });
        study = (await client.GetFromJsonAsync<BrainStudyDto>($"/api/app/brain-study/{seed.Study.Id}"))!;
        Assert.Equal(2, study.JobRequestCount);
        using var blockedDelete = new HttpRequestMessage(HttpMethod.Delete,
            $"/api/app/brain-study/{study.Id}?concurrencyStamp={Uri.EscapeDataString(study.ConcurrencyStamp)}");
        using var blocked = await client.SendAsync(blockedDelete);
        Assert.Equal(HttpStatusCode.Conflict, blocked.StatusCode);
        Assert.Contains(ResearchErrors.StudyHasActiveJobs, await blocked.Content.ReadAsStringAsync());
        SegmentationResult result = null!;
        await factory.RunAsync(async services =>
        {
            var jobs = services.GetRequiredService<ISegmentationJobRepository>();
            var completedJob = await jobs.GetAsync(job.Id);
            var startedAt = DateTime.UtcNow;
            completedJob.Start(startedAt, startedAt.AddMinutes(5), Guid.NewGuid());
            completedJob.Complete(startedAt.AddSeconds(1));
            await jobs.UpdateAsync(completedJob, autoSave: true);
            result = new SegmentationResult(Guid.NewGuid(), completedJob.Id, seed.Artifact,
                seed.Model.WeightSha256, null, null, 3, 3 / (8.0 * 8 * 2), 1, 0, 0,
                startedAt.AddSeconds(1));
            await services.GetRequiredService<ISegmentationResultRepository>()
                .InsertAsync(result, autoSave: true);
        });
        var cancelledJob = await PostAsync<SegmentationJobDto>(client,
            $"/api/app/segmentation-job/{activeJob.Id}/cancel",
            new ResearchCommandInput { ConcurrencyStamp = activeJob.ConcurrencyStamp });
        Assert.Equal(SegmentationJobStatus.Cancelled, cancelledJob.Status);
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
    public async Task Public_completion_endpoint_is_not_available_for_caller_supplied_results()
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        var seed = await SeedAsync(factory);
        using var client = factory.AuthenticatedClient(Permissions);
        var job = await PostAsync<SegmentationJobDto>(client, "/api/app/segmentation-job", new CreateSegmentationJobInput
        { StudyId = seed.Study.Id, ModelVersionId = seed.Model.Id, IdempotencyKey = "atomic-completion" });
        using var missing = await client.PostAsJsonAsync($"/api/app/segmentation-job/{job.Id}/complete",
            new { maskObjectKey = AggregateTests.ObjectKey() });
        Assert.Equal(HttpStatusCode.NotFound, missing.StatusCode);
        var unchanged = (await client.GetFromJsonAsync<SegmentationJobDto>($"/api/app/segmentation-job/{job.Id}"))!;
        Assert.Equal(SegmentationJobStatus.Pending, unchanged.Status);
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
