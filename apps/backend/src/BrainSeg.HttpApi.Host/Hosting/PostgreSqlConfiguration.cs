using Npgsql;

namespace BrainSeg.Hosting;

public static class PostgreSqlConfiguration
{
    public static void Apply(IConfiguration configuration)
    {
        if (!string.IsNullOrWhiteSpace(configuration["ConnectionStrings:Default"]))
        {
            return;
        }

        var password = configuration["POSTGRES_PASSWORD"];
        if (string.IsNullOrWhiteSpace(password))
        {
            return;
        }
        if (password.StartsWith("replace-", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Replace the example PostgreSQL password before starting the host.");
        }
        configuration["ConnectionStrings:Default"] = new NpgsqlConnectionStringBuilder
        {
            Host = configuration["POSTGRES_HOST"] ?? "localhost",
            Port = int.Parse(configuration["POSTGRES_PORT"] ?? "5432", global::System.Globalization.CultureInfo.InvariantCulture),
            Database = configuration["POSTGRES_DB"] ?? "brainseg",
            Username = configuration["POSTGRES_USER"] ?? "brainseg",
            Password = password,
            Timeout = 5,
            CommandTimeout = 30,
            IncludeErrorDetail = false
        }.ConnectionString;
    }
}
