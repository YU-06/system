namespace BrainSeg.Storage;

public interface IObjectWriteIntentManager
{
    Task RegisterAsync(string objectKey, string purpose, CancellationToken cancellationToken);
    Task CompleteInCurrentUnitOfWorkAsync(string objectKey, CancellationToken cancellationToken);
}
