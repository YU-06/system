using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace BrainSeg;

public class BrainSegDbContextFactory : IDesignTimeDbContextFactory<BrainSegDbContext>
{
    public BrainSegDbContext CreateDbContext(string[] args)
    {
        var connectionString = Environment.GetEnvironmentVariable("ConnectionStrings__Default")
            ?? "Host=localhost;Port=5432;Database=brainseg;Username=brainseg";
        var options = new DbContextOptionsBuilder<BrainSegDbContext>().UseNpgsql(connectionString).Options;
        return new BrainSegDbContext(options);
    }
}
