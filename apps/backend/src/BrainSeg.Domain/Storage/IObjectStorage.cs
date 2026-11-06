namespace BrainSeg.Storage;

public sealed record StoredObject(string ObjectKey, string Sha256, long SizeBytes);

public interface IObjectStorage
{
    Task<StoredObject> SaveAsync(Stream content, CancellationToken cancellationToken = default);
    Task<Stream> OpenReadAsync(string objectKey, CancellationToken cancellationToken = default);
    Task DeleteAsync(string objectKey, CancellationToken cancellationToken = default);
    Task<bool> IsAvailableAsync(CancellationToken cancellationToken = default);
}
