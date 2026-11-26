using System.Security.Cryptography;

namespace BrainSeg.Storage;

internal static class StoragePayload
{
    public static string ValidateKey(string objectKey)
    {
        if (objectKey.Length != 36 || !objectKey.EndsWith(".bin", StringComparison.Ordinal)
            || !Guid.TryParseExact(objectKey[..32], "N", out _))
        {
            throw new ArgumentException("Invalid object key.", nameof(objectKey));
        }
        return objectKey;
    }

    public static async Task<(string TemporaryPath, StoredObject Object)> CopyToTemporaryFileAsync(
        Stream content, string temporaryDirectory, string objectKey, long maxBytes,
        CancellationToken cancellationToken)
    {
        ValidateKey(objectKey);
        Directory.CreateDirectory(temporaryDirectory);
        var temporaryPath = Path.Combine(temporaryDirectory, $".pending-{Guid.NewGuid():N}.tmp");
        try
        {
            using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            await using var target = new FileStream(temporaryPath, FileMode.CreateNew, FileAccess.Write,
                FileShare.None, 81920, FileOptions.Asynchronous | FileOptions.SequentialScan);
            var chunk = new byte[81920];
            long size = 0;
            while (true)
            {
                var count = await content.ReadAsync(chunk, cancellationToken);
                if (count == 0) break;
                size += count;
                if (size > maxBytes)
                    throw new ArgumentException("Object exceeds the configured size limit.", nameof(content));
                hash.AppendData(chunk, 0, count);
                await target.WriteAsync(chunk.AsMemory(0, count), cancellationToken);
            }
            await target.FlushAsync(cancellationToken);
            return (temporaryPath, new StoredObject(objectKey,
                Convert.ToHexStringLower(hash.GetHashAndReset()), size));
        }
        catch
        {
            if (File.Exists(temporaryPath)) File.Delete(temporaryPath);
            throw;
        }
    }
}
