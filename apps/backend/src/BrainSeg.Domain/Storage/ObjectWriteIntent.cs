using BrainSeg.Research;
using Volo.Abp;
using Volo.Abp.Domain.Entities;

namespace BrainSeg.Storage;

public class ObjectWriteIntent : BasicAggregateRoot<Guid>
{
    public string ObjectKey { get; private set; } = string.Empty;
    public string Purpose { get; private set; } = string.Empty;
    public DateTime RequestedTime { get; private set; }
    public DateTime NextAttemptTime { get; private set; }
    public int AttemptCount { get; private set; }

    protected ObjectWriteIntent() { }

    public ObjectWriteIntent(Guid id, string objectKey, string purpose, DateTime requestedTime) : base(id)
    {
        ResearchGuard.Identifier(id, nameof(Id));
        ObjectKey = ResearchGuard.ObjectKey(objectKey, nameof(ObjectKey));
        Purpose = ResearchGuard.Token(purpose, nameof(Purpose), 32);
        RequestedTime = ResearchGuard.Utc(requestedTime);
        NextAttemptTime = RequestedTime;
    }

    public bool CanAttempt(DateTime now) => NextAttemptTime <= ResearchGuard.Utc(now);

    public void DelayNextAttempt(DateTime now)
    {
        now = ResearchGuard.Utc(now, RequestedTime);
        AttemptCount = checked(AttemptCount + 1);
        var delay = TimeSpan.FromSeconds(Math.Min(300, Math.Pow(2, Math.Min(AttemptCount, 8))));
        NextAttemptTime = now.Add(delay);
    }
}
