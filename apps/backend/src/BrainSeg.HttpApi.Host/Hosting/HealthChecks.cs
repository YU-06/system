using System.Text.Json;
using BrainSeg.Storage;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Diagnostics.HealthChecks;

namespace BrainSeg.Hosting;

public class PostgreSqlHealthCheck(BrainSegDbContext database) : IHealthCheck
{
    public async Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken cancellationToken)
    {
        try
        {
            return await database.Database.CanConnectAsync(cancellationToken)
                ? HealthCheckResult.Healthy()
                : HealthCheckResult.Unhealthy("Database unavailable.");
        }
        catch (Exception)
        {
            return HealthCheckResult.Unhealthy("Database unavailable.");
        }
    }
}

public class StorageHealthCheck(IObjectStorage storage) : IHealthCheck
{
    public async Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken cancellationToken)
    {
        try
        {
            return await storage.IsAvailableAsync(cancellationToken)
                ? HealthCheckResult.Healthy()
                : HealthCheckResult.Unhealthy("Object storage unavailable.");
        }
        catch (Exception)
        {
            return HealthCheckResult.Unhealthy("Object storage unavailable.");
        }
    }
}

public class MlHealthCheck(IHttpClientFactory clients) : IHealthCheck
{
    public async Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken cancellationToken)
    {
        try
        {
            using var response = await clients.CreateClient("ml-inference").GetAsync("/health", cancellationToken);
            return response.IsSuccessStatusCode
                ? HealthCheckResult.Healthy()
                : HealthCheckResult.Unhealthy("Inference service unavailable.");
        }
        catch (Exception)
        {
            return HealthCheckResult.Unhealthy("Inference service unavailable.");
        }
    }
}

public static class HealthResponseWriter
{
    public static Task WriteAsync(HttpContext context, HealthReport report)
    {
        context.Response.ContentType = "application/json";
        return JsonSerializer.SerializeAsync(context.Response.Body, new
        {
            status = report.Status.ToString(),
            correlationId = context.Response.Headers[SafeCorrelationMiddleware.HeaderName].ToString(),
            checks = report.Entries.ToDictionary(entry => entry.Key, entry => entry.Value.Status.ToString())
        }, cancellationToken: context.RequestAborted);
    }
}
