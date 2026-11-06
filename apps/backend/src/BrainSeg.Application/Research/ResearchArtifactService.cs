using System.Buffers.Binary;
using System.IO.Compression;
using System.Security.Cryptography;
using BrainSeg.Storage;
using Volo.Abp;
using Volo.Abp.Content;
using Volo.Abp.DependencyInjection;

namespace BrainSeg.Research;

public sealed record ValidatedStudyFile(byte[] OriginalBytes, string Sha256, int Width, int Height);

public class ResearchArtifactService(IObjectStorage storage) : ITransientDependency
{
    private const int MaxFileBytes = 64 * 1024 * 1024;
    private const int MaxExpandedBytes = 128 * 1024 * 1024;

    public async Task<ValidatedStudyFile> ReadStudyAsync(IRemoteStreamContent file, int sliceIndex,
        CancellationToken cancellationToken)
    {
        var name = (file.FileName ?? string.Empty).ToLowerInvariant();
        if (!name.EndsWith(".nii", StringComparison.Ordinal) && !name.EndsWith(".nii.gz", StringComparison.Ordinal)
            || file.ContentType is not ("application/octet-stream" or "application/gzip" or "application/x-gzip" or "application/x-nifti"))
        {
            throw new BusinessException(ResearchErrors.InvalidFile);
        }
        await using var stream = file.GetStream();
        var original = await ReadBoundedAsync(stream, MaxFileBytes, cancellationToken);
        var bytes = original;
        if (name.EndsWith(".gz", StringComparison.Ordinal))
        {
            try
            {
                using var compressed = new MemoryStream(original, writable: false);
                await using var decompressor = new GZipStream(compressed, CompressionMode.Decompress);
                bytes = await ReadBoundedAsync(decompressor, MaxExpandedBytes, cancellationToken);
            }
            catch (InvalidDataException)
            {
                throw new BusinessException(ResearchErrors.InvalidFile);
            }
        }
        if (bytes.Length < 352 || !bytes.AsSpan(344, 4).SequenceEqual("n+1\0"u8))
        {
            throw new BusinessException(ResearchErrors.InvalidFile);
        }
        var littleEndian = BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(0, 4)) == 348;
        if (!littleEndian && BinaryPrimitives.ReadInt32BigEndian(bytes.AsSpan(0, 4)) != 348)
        {
            throw new BusinessException(ResearchErrors.InvalidFile);
        }
        short ReadShort(int offset) => littleEndian
            ? BinaryPrimitives.ReadInt16LittleEndian(bytes.AsSpan(offset, 2))
            : BinaryPrimitives.ReadInt16BigEndian(bytes.AsSpan(offset, 2));
        var width = ReadShort(42);
        var height = ReadShort(44);
        var depth = ReadShort(46);
        var bits = ReadShort(72);
        var expectedBits = ReadShort(70) switch
        {
            2 or 256 => 8,
            4 or 512 => 16,
            8 or 16 or 768 => 32,
            64 => 64,
            _ => 0
        };
        var offsetBits = littleEndian ? BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(108, 4))
            : BinaryPrimitives.ReadInt32BigEndian(bytes.AsSpan(108, 4));
        var offset = BitConverter.Int32BitsToSingle(offsetBits);
        if (ReadShort(40) != 3 || width is < 1 or > 512 || height is < 1 or > 512 || depth is < 1 or > 512
            || sliceIndex < 0 || sliceIndex >= depth || (long)width * height * depth > 16777216
            || bits != expectedBits || bits == 0 || !float.IsFinite(offset) || offset < 352
            || offset > MaxExpandedBytes || offset != Math.Truncate(offset)
            || offset + (long)width * height * depth * bits / 8 > bytes.Length)
        {
            throw new BusinessException(ResearchErrors.InvalidFile);
        }
        return new ValidatedStudyFile(original, Convert.ToHexStringLower(SHA256.HashData(original)), width, height);
    }

    public async Task VerifyAsync(string key, string? expectedHash, CancellationToken cancellationToken)
    {
        try
        {
            await using var stream = await storage.OpenReadAsync(key, cancellationToken);
            var bytes = await ReadBoundedAsync(stream, MaxFileBytes, cancellationToken);
            if (expectedHash is not null && !string.Equals(Convert.ToHexStringLower(SHA256.HashData(bytes)), expectedHash,
                StringComparison.OrdinalIgnoreCase))
            {
                throw new BusinessException(ResearchErrors.ArtifactHashMismatch);
            }
        }
        catch (Exception exception) when (exception is not (BusinessException or OperationCanceledException))
        {
            throw new BusinessException(ResearchErrors.ArtifactUnavailable);
        }
    }

    private static async Task<byte[]> ReadBoundedAsync(Stream stream, int maximum, CancellationToken cancellationToken)
    {
        using var buffer = new MemoryStream();
        var chunk = new byte[81920];
        while (true)
        {
            var count = await stream.ReadAsync(chunk, cancellationToken);
            if (count == 0) return buffer.ToArray();
            if (buffer.Length + count > maximum) throw new BusinessException(ResearchErrors.UploadTooLarge);
            await buffer.WriteAsync(chunk.AsMemory(0, count), cancellationToken);
        }
    }
}
