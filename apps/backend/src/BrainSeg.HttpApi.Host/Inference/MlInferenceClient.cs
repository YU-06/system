using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using BrainSeg.Storage;
using Microsoft.Extensions.Options;
using Polly.Timeout;

namespace BrainSeg.Inference;

public sealed class MlInferenceOptions
{
    public const string SectionName = "MlInference";
    public string BaseUrl { get; set; } = "http://localhost:8000";
    public string? ApiKey { get; set; }
    public int RequestTimeoutSeconds { get; set; } = 150;
}

public sealed class MlInferenceClient(HttpClient client, IObjectStorage storage,
    IOptions<MlInferenceOptions> options) : IMlInferenceClient
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true
    };

    public async Task<InferenceSegmentResponse> SegmentAsync(string inputObjectKey,
        string expectedInputSha256, string requestId, string correlationId,
        CancellationToken cancellationToken)
    {
        for (var attempt = 0; ; attempt++)
        {
            try
            {
                using var input = await storage.OpenReadAsync(inputObjectKey, cancellationToken);
                using var form = new MultipartFormDataContent();
                form.Add(new StreamContent(input), "file", "volume.nii");
                form.Add(new StringContent(requestId), "requestId");
                using var request = CreateRequest(HttpMethod.Post, "/v1/segment", correlationId, form);
                using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead,
                    cancellationToken);
                if (IsRetryable(response.StatusCode) && attempt == 0) continue;
                await EnsureSuccessAsync(response, cancellationToken);
                var result = await response.Content.ReadFromJsonAsync<InferenceSegmentResponse>(
                    JsonOptions, cancellationToken);
                if (result is null || !string.Equals(result.InputSha256, expectedInputSha256,
                    StringComparison.OrdinalIgnoreCase) || result.RequestId != requestId
                    || result.CorrelationId != correlationId)
                {
                    throw new InferenceClientException("INFERENCE_RESPONSE_MISMATCH", false,
                        response.StatusCode);
                }
                return result;
            }
            catch (HttpRequestException) when (attempt == 0 && !cancellationToken.IsCancellationRequested)
            {
            }
            catch (HttpRequestException) when (!cancellationToken.IsCancellationRequested)
            {
                throw new InferenceClientException("INFERENCE_UNAVAILABLE", true);
            }
            catch (TaskCanceledException) when (attempt == 0 && !cancellationToken.IsCancellationRequested)
            {
            }
            catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                throw new InferenceClientException("INFERENCE_TIMEOUT", true);
            }
            catch (TimeoutRejectedException) when (!cancellationToken.IsCancellationRequested && attempt == 0)
            {
            }
            catch (TimeoutRejectedException) when (!cancellationToken.IsCancellationRequested)
            {
                throw new InferenceClientException("INFERENCE_TIMEOUT", true);
            }
        }
    }

    public async Task<InferencePredictionDownload> OpenPredictionAsync(string predictionObjectKey,
        string correlationId, CancellationToken cancellationToken)
    {
        var request = CreateRequest(HttpMethod.Get,
            $"/v1/predictions/{Uri.EscapeDataString(predictionObjectKey)}", correlationId);
        HttpResponseMessage response;
        try
        {
            response = await SendRequestAsync(request, cancellationToken);
        }
        finally
        {
            request.Dispose();
        }
        try
        {
            await EnsureSuccessAsync(response, cancellationToken);
            var digest = response.Headers.TryGetValues("X-Prediction-Sha256", out var values)
                ? values.SingleOrDefault() : null;
            if (digest is null || digest.Length != 64 || !digest.All(Uri.IsHexDigit))
                throw new InferenceClientException("PREDICTION_HASH_MISSING", false, response.StatusCode);
            var content = await response.Content.ReadAsStreamAsync(cancellationToken);
            return new InferencePredictionDownload(response, content, digest.ToLowerInvariant());
        }
        catch
        {
            response.Dispose();
            throw;
        }
    }

    public async Task<InferenceEvaluationResponse> EvaluateAsync(string inputObjectKey,
        string groundTruthObjectKey, string predictionObjectKey, string correlationId,
        CancellationToken cancellationToken)
    {
        await using var input = await storage.OpenReadAsync(inputObjectKey, cancellationToken);
        await using var groundTruth = await storage.OpenReadAsync(groundTruthObjectKey, cancellationToken);
        using var form = new MultipartFormDataContent();
        form.Add(new StreamContent(input), "file", "volume.nii");
        form.Add(new StreamContent(groundTruth), "label", "labels.nii");
        form.Add(new StringContent(predictionObjectKey), "predictionObjectKey");
        form.Add(new StringContent("whole-tumor-v1"), "evaluationProtocol");
        using var request = CreateRequest(HttpMethod.Post, "/v1/evaluate", correlationId, form);
        using var response = await SendRequestAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        var result = await response.Content.ReadFromJsonAsync<InferenceEvaluationResponse>(
            JsonOptions, cancellationToken);
        return result ?? throw new InferenceClientException("EVALUATION_RESPONSE_INVALID", false,
            response.StatusCode);
    }

    private HttpRequestMessage CreateRequest(HttpMethod method, string path, string correlationId,
        HttpContent? content = null)
    {
        var request = new HttpRequestMessage(method, path) { Content = content };
        request.Headers.TryAddWithoutValidation("X-Correlation-Id", correlationId);
        if (!string.IsNullOrWhiteSpace(options.Value.ApiKey))
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", options.Value.ApiKey);
        return request;
    }

    private async Task<HttpResponseMessage> SendRequestAsync(HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        try
        {
            return await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead,
                cancellationToken);
        }
        catch (HttpRequestException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new InferenceClientException("INFERENCE_UNAVAILABLE", true);
        }
        catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new InferenceClientException("INFERENCE_TIMEOUT", true);
        }
        catch (TimeoutRejectedException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new InferenceClientException("INFERENCE_TIMEOUT", true);
        }
    }

    private static bool IsRetryable(HttpStatusCode statusCode) =>
        statusCode is HttpStatusCode.RequestTimeout or HttpStatusCode.TooManyRequests
            or HttpStatusCode.BadGateway or HttpStatusCode.ServiceUnavailable
            or HttpStatusCode.GatewayTimeout;

    private static async Task EnsureSuccessAsync(HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        if (response.IsSuccessStatusCode) return;
        var code = $"HTTP_{(int)response.StatusCode}";
        try
        {
            using var document = await JsonDocument.ParseAsync(
                await response.Content.ReadAsStreamAsync(cancellationToken), cancellationToken: cancellationToken);
            if (document.RootElement.TryGetProperty("error", out var error)
                && error.TryGetProperty("code", out var codeValue)
                && codeValue.ValueKind == JsonValueKind.String)
            {
                code = codeValue.GetString() ?? code;
            }
        }
        catch (JsonException)
        {
        }
        throw new InferenceClientException(code, IsRetryable(response.StatusCode), response.StatusCode);
    }
}
