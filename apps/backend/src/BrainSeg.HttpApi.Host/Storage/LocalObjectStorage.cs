namespace BrainSeg.Storage;

public sealed class LocalObjectStorage(IConfiguration configuration) : IObjectStorage
{
    private readonly string rootPath = Path.GetFullPath(configuration["ObjectStorage:RootPath"] ?? "data/objects");
    private readonly long maxBytes = configuration.GetValue("ObjectStorage:MaxObjectBytes", 67108864L);

    public Task<StoredObject> SaveAsync(Stream content, CancellationToken cancellationToken = default) =>
        SaveAsync($"{Guid.NewGuid():N}.bin", content, cancellationToken);

    public async Task<StoredObject> SaveAsync(string objectKey, Stream content,
        CancellationToken cancellationToken = default)
    {
        Directory.CreateDirectory(rootPath);
        var payload = await StoragePayload.CopyToTemporaryFileAsync(content, rootPath, objectKey, maxBytes, cancellationToken);
        try
        {
            File.Move(payload.TemporaryPath, Path.Combine(rootPath, objectKey));
            return payload.Object;
        }
        catch
        {
            if (File.Exists(payload.TemporaryPath)) File.Delete(payload.TemporaryPath);
            throw;
        }
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
