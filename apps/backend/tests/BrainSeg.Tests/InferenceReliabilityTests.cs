using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using BrainSeg.Inference;
using BrainSeg.Research;
using BrainSeg.Storage;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Http.Resilience;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Polly.CircuitBreaker;
using Xunit;

namespace BrainSeg.Tests;

public sealed class InferenceReliabilityTests
{
    [Fact]
    public async Task Segment_retry_reuses_request_and_correlation_ids()
    {
        const string inputHash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        const string requestId = "idempotent-request";
        const string correlationId = "correlation-123";
        var response = new InferenceSegmentResponse(
            "1.0.0", "UNet", "research", "flair-v1", 256, 0.5, correlationId, requestId,
            inputHash, new string('b', 64), new string('c', 64), "prediction.nii.gz",
            new string('d', 64), [8, 8, 1], "original", 0, 0,
            new InferenceTimings(1, 2, 3));
        var handler = new RetryOnceHandler(response);
        using var http = new HttpClient(handler) { BaseAddress = new Uri("http://inference.test") };
        var client = new MlInferenceClient(
            http,
            new MemoryObjectStorage("input.nii", Encoding.UTF8.GetBytes("synthetic-nifti")),
            Options.Create(new MlInferenceOptions()));

        var actual = await client.SegmentAsync("input.nii", inputHash, requestId, correlationId,
            CancellationToken.None);

        Assert.Equal(requestId, actual.RequestId);
        Assert.Equal(2, handler.Requests.Count);
        Assert.All(handler.Requests, captured =>
        {
            Assert.Equal(correlationId, captured.CorrelationId);
            Assert.Contains(requestId, captured.Body);
        });
    }

    [Fact]
    public async Task Standard_http_resilience_pipeline_opens_circuit_after_failures()
    {
        var handler = new CountingUnavailableHandler();
        var services = new ServiceCollection();
        services.AddHttpClient("resilience")
            .ConfigurePrimaryHttpMessageHandler(() => handler)
            .AddStandardResilienceHandler(options =>
            {
                options.Retry.MaxRetryAttempts = 1;
                options.Retry.DisableForUnsafeHttpMethods();
                options.AttemptTimeout.Timeout = TimeSpan.FromSeconds(1);
                options.CircuitBreaker.MinimumThroughput = 2;
                options.CircuitBreaker.FailureRatio = 0.5;
                options.CircuitBreaker.SamplingDuration = TimeSpan.FromSeconds(3);
                options.CircuitBreaker.BreakDuration = TimeSpan.FromSeconds(5);
            });
        using var provider = services.BuildServiceProvider();
        using var http = provider.GetRequiredService<IHttpClientFactory>().CreateClient("resilience");

        using var first = await http.PostAsync("http://inference.test/segment", null);
        using var second = await http.PostAsync("http://inference.test/segment", null);
        await Assert.ThrowsAsync<BrokenCircuitException>(
            () => http.PostAsync("http://inference.test/segment", null));

        Assert.Equal(2, handler.RequestCount);
    }

    [Fact]
    public async Task Worker_recovers_an_expired_claim_and_retries_before_processing()
    {
        using var factory = new RecoveringResearchFactory();
        await factory.InitializeAsync();
        var seed = await Research.WorkflowTests.SeedAsync(factory);
        var now = DateTime.UtcNow.AddMinutes(-20);
        var jobId = Guid.NewGuid();
        await factory.RunAsync(async services =>
        {
            var job = new SegmentationJob(
                jobId,
                seed.Study.Id,
                seed.Model.Id,
                seed.Study.OriginalFileSha256,
                seed.Model.Architecture,
                seed.Model.SemanticVersion,
                seed.Model.PreprocessingVersion,
                seed.Model.WeightSha256,
                seed.Model.InputSize,
                seed.Model.Threshold,
                Research.ResearchFactory.UserId,
                $"recover-{Guid.NewGuid():N}",
                $"recover-correlation-{Guid.NewGuid():N}",
                now.AddMinutes(-1));
            job.Start(now, now.AddMinutes(1), Guid.NewGuid());
            await services.GetRequiredService<ISegmentationJobRepository>()
                .InsertAsync(job, autoSave: true);
        });

        using var worker = new InferenceJobWorker(
            factory.Services.GetRequiredService<IServiceScopeFactory>(),
            NullLogger<InferenceJobWorker>.Instance);
        await worker.StartAsync(CancellationToken.None);
        try
        {
            var processedId = await factory.Processor.Started.Task.WaitAsync(TimeSpan.FromSeconds(10));
            Assert.Equal(jobId, processedId);
            await factory.RunAsync(async services =>
            {
                var recovered = await services.GetRequiredService<ISegmentationJobRepository>()
                    .GetAsync(jobId);
                Assert.Equal(SegmentationJobStatus.Running, recovered.Status);
                Assert.Equal(1, recovered.RetryCount);
            });
        }
        finally
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            await worker.StopAsync(timeout.Token);
        }
    }

    private sealed class RetryOnceHandler(InferenceSegmentResponse response) : HttpMessageHandler
    {
        public ConcurrentBag<(string? CorrelationId, string Body)> Requests { get; } = [];
        private int callCount;

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var body = await request.Content!.ReadAsStringAsync(cancellationToken);
            Requests.Add((request.Headers.GetValues("X-Correlation-Id").Single(), body));
            if (Interlocked.Increment(ref callCount) == 1)
                return new HttpResponseMessage(HttpStatusCode.ServiceUnavailable);
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = JsonContent.Create(response)
            };
        }
    }

    private sealed class CountingUnavailableHandler : HttpMessageHandler
    {
        private int requestCount;
        public int RequestCount => Volatile.Read(ref requestCount);

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Interlocked.Increment(ref requestCount);
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.ServiceUnavailable));
        }
    }

    private sealed class MemoryObjectStorage(string key, byte[] payload) : IObjectStorage
    {
        public Task<StoredObject> SaveAsync(Stream content, CancellationToken cancellationToken = default) =>
            SaveAsync(Guid.NewGuid().ToString("N"), content, cancellationToken);

        public async Task<StoredObject> SaveAsync(
            string objectKey, Stream content, CancellationToken cancellationToken = default)
        {
            using var memory = new MemoryStream();
            await content.CopyToAsync(memory, cancellationToken);
            var bytes = memory.ToArray();
            return new StoredObject(objectKey, Convert.ToHexStringLower(SHA256.HashData(bytes)), bytes.Length);
        }

        public Task<Stream> OpenReadAsync(string objectKey, CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (objectKey != key) throw new FileNotFoundException();
            return Task.FromResult<Stream>(new MemoryStream(payload, writable: false));
        }

        public Task DeleteAsync(string objectKey, CancellationToken cancellationToken = default) =>
            Task.CompletedTask;

        public Task<bool> IsAvailableAsync(CancellationToken cancellationToken = default) =>
            Task.FromResult(true);
    }

    private sealed class RecoveringResearchFactory : Research.ResearchFactory
    {
        public WaitingProcessor Processor { get; } = new();

        protected override void ConfigureWebHost(IWebHostBuilder builder)
        {
            base.ConfigureWebHost(builder);
            builder.ConfigureTestServices(services =>
                services.Replace(ServiceDescriptor.Singleton<IInferenceJobProcessor>(Processor)));
        }
    }

    private sealed class WaitingProcessor : IInferenceJobProcessor
    {
        public TaskCompletionSource<Guid> Started { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public Task ExecuteAsync(Guid jobId, Guid claimToken, CancellationToken cancellationToken)
        {
            Started.TrySetResult(jobId);
            return Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
        }
    }
}
