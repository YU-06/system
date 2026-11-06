using System.Text.Json;
using System.Text.RegularExpressions;
using Volo.Abp;

namespace BrainSeg.Research;

internal static class ResearchGuard
{
    public static Guid Identifier(Guid value, string field)
    {
        if (value == Guid.Empty)
        {
            throw new BusinessException(ResearchErrors.InvalidInput).WithData("Field", field);
        }
        return value;
    }

    public static string Text(string? value, string field, int maxLength)
    {
        var result = value?.Trim();
        if (string.IsNullOrEmpty(result) || result.Length > maxLength)
        {
            throw new BusinessException(ResearchErrors.InvalidInput).WithData("Field", field);
        }
        return result;
    }

    public static string Token(string? value, string field, int maxLength = 64)
    {
        var result = Text(value, field, maxLength);
        if (!result.All(character => char.IsAsciiLetterOrDigit(character) || character is '-' or '_'))
        {
            throw new BusinessException(ResearchErrors.InvalidInput).WithData("Field", field);
        }
        return result;
    }

    public static DateTime Utc(DateTime value, DateTime? notBefore = null)
    {
        if (value.Kind != DateTimeKind.Utc || notBefore.HasValue && value < notBefore.Value)
        {
            throw new BusinessException(ResearchErrors.InvalidTimestamp);
        }
        return value;
    }

    public static string Sha256(string value, string field)
    {
        if (value.Length != 64 || !value.All(Uri.IsHexDigit))
        {
            throw new BusinessException(ResearchErrors.InvalidInput).WithData("Field", field);
        }
        return value.ToLowerInvariant();
    }

    public static string ObjectKey(string value, string field)
    {
        var result = Text(value, field, 512);
        if (result.Split('/').Any(segment => segment is "" or "." or "..")
            || !result.All(character => char.IsAsciiLetterOrDigit(character) || character is '/' or '.' or '-' or '_'))
        {
            throw new BusinessException(ResearchErrors.InvalidInput).WithData("Field", field);
        }
        return result;
    }

    public static string Version(string value)
    {
        var result = Text(value, "SemanticVersion", 64);
        if (!Regex.IsMatch(result,
            @"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$",
            RegexOptions.CultureInvariant | RegexOptions.NonBacktracking))
        {
            throw new BusinessException(ResearchErrors.InvalidInput).WithData("Field", "SemanticVersion");
        }
        return result;
    }

    public static string MetricsJson(string value)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length > 16384)
        {
            throw new BusinessException(ResearchErrors.InvalidMetrics);
        }
        try
        {
            using var document = JsonDocument.Parse(value, new JsonDocumentOptions { MaxDepth = 16 });
            if (document.RootElement.ValueKind != JsonValueKind.Object)
            {
                throw new BusinessException(ResearchErrors.InvalidMetrics);
            }
            return JsonSerializer.Serialize(document.RootElement);
        }
        catch (JsonException)
        {
            throw new BusinessException(ResearchErrors.InvalidMetrics);
        }
    }

    public static double Nonnegative(double value, string field)
    {
        if (!double.IsFinite(value) || value < 0)
        {
            throw new BusinessException(ResearchErrors.InvalidInput).WithData("Field", field);
        }
        return value;
    }

    public static double? Metric(double? value)
    {
        if (value.HasValue && (!double.IsFinite(value.Value) || value < 0 || value > 1))
        {
            throw new BusinessException(ResearchErrors.InvalidMetrics);
        }
        return value;
    }
}
