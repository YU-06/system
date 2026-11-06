using Volo.Abp.Tracing;

namespace BrainSeg.Hosting;

public class CorrelationIdHandler(ICorrelationIdProvider correlationIdProvider) : DelegatingHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        request.Headers.Remove(SafeCorrelationMiddleware.HeaderName);
        request.Headers.TryAddWithoutValidation(SafeCorrelationMiddleware.HeaderName, correlationIdProvider.Get());
        return base.SendAsync(request, cancellationToken);
    }
}
