using BrainSeg;
using BrainSeg.Hosting;
using Microsoft.EntityFrameworkCore;
using Serilog;
using Serilog.Formatting.Compact;

DotNetEnv.Env.NoClobber().TraversePath().Load();
var builder = WebApplication.CreateBuilder(args);
PostgreSqlConfiguration.Apply(builder.Configuration);
builder.Host.UseAutofac();
builder.Host.UseSerilog((context, configuration) => configuration
    .MinimumLevel.Information()
    .MinimumLevel.Override("Microsoft", Serilog.Events.LogEventLevel.Warning)
    .MinimumLevel.Override("Volo.Abp", Serilog.Events.LogEventLevel.Warning)
    .Enrich.FromLogContext()
    .Enrich.WithProperty("Service", "brainseg-backend")
    .WriteTo.Console(new RenderedCompactJsonFormatter()));
await builder.AddApplicationAsync<BrainSegHttpApiHostModule>();
var app = builder.Build();
await app.InitializeApplicationAsync();
if (args.Contains("--migrate", StringComparer.Ordinal))
{
    await using var scope = app.Services.CreateAsyncScope();
    await scope.ServiceProvider.GetRequiredService<BrainSegDbContext>().Database.MigrateAsync();
    app.Logger.LogInformation("Database migrations completed");
    return;
}
await app.RunAsync();

public partial class Program;
