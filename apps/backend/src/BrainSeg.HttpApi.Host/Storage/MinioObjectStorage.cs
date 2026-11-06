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

    public async Task<StoredObject> SaveAsync(Stream content, CancellationToken cancellationToken = default)
    {
        var payload = await StoragePayload.ReadAsync(content, maxBytes, cancellationToken);
        if (!await client.BucketExistsAsync(new BucketExistsArgs().WithBucket(bucket), cancellationToken))
        {
            await client.MakeBucketAsync(new MakeBucketArgs().WithBucket(bucket), cancellationToken);
        }
        using var stream = new MemoryStream(payload.Bytes, writable: false);
        await client.PutObjectAsync(new PutObjectArgs().WithBucket(bucket).WithObject(payload.Object.ObjectKey)
            .WithStreamData(stream).WithObjectSize(stream.Length).WithContentType("application/octet-stream"), cancellationToken);
        return payload.Object;
    }

    public async Task<Stream> OpenReadAsync(string objectKey, CancellationToken cancellationToken = default)
    {
        var result = new MemoryStream();
        try
        {
            await client.GetObjectAsync(new GetObjectArgs().WithBucket(bucket)
                .WithObject(StoragePayload.ValidateKey(objectKey)).WithCallbackStream(stream => stream.CopyTo(result)), cancellationToken);
            result.Position = 0;
            return result;
        }
        catch
        {
            await result.DisposeAsync();
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
