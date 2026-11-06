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

    public static async Task<(byte[] Bytes, StoredObject Object)> ReadAsync(
        Stream content, long maxBytes, CancellationToken cancellationToken)
    {
        using var buffer = new MemoryStream();
        var chunk = new byte[81920];
        while (true)
        {
            var count = await content.ReadAsync(chunk, cancellationToken);
            if (count == 0)
            {
                break;
            }
            if (buffer.Length + count > maxBytes)
            {
                throw new ArgumentException("Object exceeds the configured size limit.", nameof(content));
            }
            await buffer.WriteAsync(chunk.AsMemory(0, count), cancellationToken);
        }
        var bytes = buffer.ToArray();
        var storedObject = new StoredObject($"{Guid.NewGuid():N}.bin",
            Convert.ToHexStringLower(SHA256.HashData(bytes)), bytes.LongLength);
        return (bytes, storedObject);
    }
}
