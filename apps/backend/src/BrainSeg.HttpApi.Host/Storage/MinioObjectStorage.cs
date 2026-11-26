using Minio;
using Minio.DataModel.Args;

namespace BrainSeg.Storage;

public sealed class MinioObjectStorage : IObjectStorage, IDisposable
{
    private readonly IMinioClient client;
    private readonly string bucket;
    private readonly long maxBytes;

    public MinioObjectStorage(IConfiguration configuration)
    {
        var endpoint = new Uri(configuration["ObjectStorage:Endpoint"] ?? "http://localhost:9000");
        bucket = configuration["ObjectStorage:Bucket"] ?? "brainseg";
        maxBytes = configuration.GetValue("ObjectStorage:MaxObjectBytes", 67108864L);
        client = new MinioClient().WithEndpoint(endpoint.Host, endpoint.Port)
            .WithCredentials(configuration["MINIO_ROOT_USER"], configuration["MINIO_ROOT_PASSWORD"])
            .WithSSL(endpoint.Scheme == Uri.UriSchemeHttps).Build();
    }

    public Task<StoredObject> SaveAsync(Stream content, CancellationToken cancellationToken = default) =>
        SaveAsync($"{Guid.NewGuid():N}.bin", content, cancellationToken);

    public async Task<StoredObject> SaveAsync(string objectKey, Stream content,
        CancellationToken cancellationToken = default)
    {
        var payload = await StoragePayload.CopyToTemporaryFileAsync(content, Path.GetTempPath(),
            objectKey, maxBytes, cancellationToken);
        try
        {
            if (!await client.BucketExistsAsync(new BucketExistsArgs().WithBucket(bucket), cancellationToken))
            {
                await client.MakeBucketAsync(new MakeBucketArgs().WithBucket(bucket), cancellationToken);
            }
            await using var stream = new FileStream(payload.TemporaryPath, FileMode.Open, FileAccess.Read,
                FileShare.Read, 81920, FileOptions.Asynchronous | FileOptions.SequentialScan);
            await client.PutObjectAsync(new PutObjectArgs().WithBucket(bucket).WithObject(payload.Object.ObjectKey)
                .WithStreamData(stream).WithObjectSize(payload.Object.SizeBytes)
                .WithContentType("application/octet-stream"), cancellationToken);
            return payload.Object;
        }
        finally
        {
            File.Delete(payload.TemporaryPath);
        }
    }

    public async Task<Stream> OpenReadAsync(string objectKey, CancellationToken cancellationToken = default)
    {
        var temporaryPath = Path.Combine(Path.GetTempPath(), $"brainseg-{Guid.NewGuid():N}.tmp");
        try
        {
            await client.GetObjectAsync(new GetObjectArgs().WithBucket(bucket)
                .WithObject(StoragePayload.ValidateKey(objectKey))
                .WithCallbackStream(stream =>
                {
                    using var target = new FileStream(temporaryPath, FileMode.CreateNew, FileAccess.Write,
                        FileShare.None, 81920, FileOptions.SequentialScan);
                    stream.CopyTo(target, 81920);
                }), cancellationToken);
            return new FileStream(temporaryPath, FileMode.Open, FileAccess.Read, FileShare.Read,
                81920, FileOptions.Asynchronous | FileOptions.SequentialScan | FileOptions.DeleteOnClose);
        }
        catch
        {
            if (File.Exists(temporaryPath)) File.Delete(temporaryPath);
            throw;
        }
    }

    public Task DeleteAsync(string objectKey, CancellationToken cancellationToken = default) =>
        client.RemoveObjectAsync(new RemoveObjectArgs().WithBucket(bucket)
            .WithObject(StoragePayload.ValidateKey(objectKey)), cancellationToken);

    public async Task<bool> IsAvailableAsync(CancellationToken cancellationToken = default)
    {
        await client.ListBucketsAsync(cancellationToken);
        return true;
    }

    public void Dispose() => client.Dispose();
}
