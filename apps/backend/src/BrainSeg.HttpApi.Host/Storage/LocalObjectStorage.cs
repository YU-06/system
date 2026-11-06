namespace BrainSeg.Storage;

public sealed class LocalObjectStorage(IConfiguration configuration) : IObjectStorage
{
    private readonly string rootPath = Path.GetFullPath(configuration["ObjectStorage:RootPath"] ?? "data/objects");
    private readonly long maxBytes = configuration.GetValue("ObjectStorage:MaxObjectBytes", 67108864L);

    public async Task<StoredObject> SaveAsync(Stream content, CancellationToken cancellationToken = default)
    {
        var payload = await StoragePayload.ReadAsync(content, maxBytes, cancellationToken);
        Directory.CreateDirectory(rootPath);
        await File.WriteAllBytesAsync(Path.Combine(rootPath, payload.Object.ObjectKey), payload.Bytes, cancellationToken);
        return payload.Object;
    }

    public Task<Stream> OpenReadAsync(string objectKey, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        Stream stream = File.OpenRead(Path.Combine(rootPath, StoragePayload.ValidateKey(objectKey)));
        return Task.FromResult(stream);
    }

    public Task DeleteAsync(string objectKey, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        File.Delete(Path.Combine(rootPath, StoragePayload.ValidateKey(objectKey)));
        return Task.CompletedTask;
    }

    public Task<bool> IsAvailableAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        Directory.CreateDirectory(rootPath);
        return Task.FromResult(Directory.Exists(rootPath));
    }
}
