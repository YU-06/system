using System.Net;
using System.Net.Http.Json;
using BrainSeg.System;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace BrainSeg.Tests;

public class BrainSegFactory : WebApplicationFactory<Program>
{
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Testing");
        builder.ConfigureAppConfiguration((_, configuration) => configuration.AddInMemoryCollection(
            new Dictionary<string, string?>
            {
                ["ConnectionStrings:Default"] = "Host=127.0.0.1;Port=1;Database=brainseg;Username=test;Timeout=1",
                ["ObjectStorage:Provider"] = "Local",
                ["ObjectStorage:RootPath"] = Path.Combine(Path.GetTempPath(), "brainseg-host-tests"),
                ["MlInference:BaseUrl"] = "http://127.0.0.1:1"
            }));
    }
}

public class HostTests(BrainSegFactory factory) : IClassFixture<BrainSegFactory>
{
    [Fact]
    public async Task Liveness_does_not_require_external_services()
    {
        using var client = factory.CreateClient();
        using var response = await client.GetAsync("/health");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Contains("Healthy", await response.Content.ReadAsStringAsync());
        Assert.NotEmpty(response.Headers.GetValues("X-Correlation-Id"));
    }

    [Fact]
    public async Task Readiness_returns_safe_503_when_dependencies_are_unavailable()
    {
        using var client = factory.CreateClient();
        using var response = await client.GetAsync("/ready");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        var body = await response.Content.ReadAsStringAsync();
        Assert.Contains("Unhealthy", body);
        Assert.DoesNotContain("Password", body, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("127.0.0.1", body);
        Assert.DoesNotContain("StackTrace", body);
    }

    [Fact]
    public async Task Public_status_contains_research_scope_and_utc_time()
    {
        using var client = factory.CreateClient();
        var result = await client.GetFromJsonAsync<SystemStatusDto>("/api/app/system");
        Assert.NotNull(result);
        Assert.Equal("BraTS 2020", result.Dataset);
        Assert.Equal("T2-FLAIR", result.Modality);
        Assert.Contains("Not for clinical diagnosis", result.Disclaimer);
        Assert.Equal(DateTimeKind.Utc, result.ServerTimeUtc.Kind);
    }

    [Theory]
    [InlineData("research-request_123", true)]
    [InlineData("unsafe id", false)]
    public async Task Correlation_id_is_preserved_only_when_safe(string candidate, bool preserved)
    {
        using var client = factory.CreateClient();
        client.DefaultRequestHeaders.TryAddWithoutValidation("X-Correlation-Id", candidate);
        using var response = await client.GetAsync("/health");
        var actual = response.Headers.GetValues("X-Correlation-Id").Single();
        Assert.Equal(preserved, actual == candidate);
    }

    [Fact]
    public async Task Identity_management_requires_authentication()
    {
        using var client = factory.CreateClient();
        using var response = await client.GetAsync("/api/identity/users");
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [Fact]
    public async Task Swagger_exposes_the_application_service()
    {
        using var client = factory.CreateClient();
        var swagger = await client.GetStringAsync("/swagger/v1/swagger.json");
        Assert.Contains("/api/app/system", swagger);
        Assert.Contains("Not for clinical diagnosis", swagger);
    }
}
