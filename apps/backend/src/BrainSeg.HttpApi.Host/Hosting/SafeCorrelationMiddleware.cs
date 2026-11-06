using Serilog.Context;

namespace BrainSeg.Hosting;

public class SafeCorrelationMiddleware(RequestDelegate next)
{
    public const string HeaderName = "X-Correlation-Id";

    public async Task InvokeAsync(HttpContext context)
    {
        var candidate = context.Request.Headers[HeaderName].ToString();
        var correlationId = candidate.Length is > 0 and <= 64
            && candidate.All(character => char.IsAsciiLetterOrDigit(character) || character is '-' or '_')
            ? candidate
            : Guid.NewGuid().ToString("N");
        context.Request.Headers[HeaderName] = correlationId;
        context.Response.Headers[HeaderName] = correlationId;
        using (LogContext.PushProperty("CorrelationId", correlationId))
        {
            await next(context);
        }
    }
}
