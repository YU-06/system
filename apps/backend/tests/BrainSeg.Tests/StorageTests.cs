using System.Security.Cryptography;
using System.Text;
using BrainSeg.Storage;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace BrainSeg.Tests;

public sealed class StorageTests : IDisposable
{
    private readonly string rootPath = Path.Combine(Path.GetTempPath(), "brainseg-storage-tests", Guid.NewGuid().ToString("N"));

    private LocalObjectStorage CreateStorage(long maxBytes = 1024) => new(new ConfigurationBuilder()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["ObjectStorage:RootPath"] = rootPath,
            ["ObjectStorage:MaxObjectBytes"] = maxBytes.ToString(global::System.Globalization.CultureInfo.InvariantCulture)
        }).Build());

    [Fact]
    public async Task Stores_generated_keys_hashes_and_roundtrips_content()
    {
        var storage = CreateStorage();
        var bytes = Encoding.UTF8.GetBytes("non-medical test fixture");
        using var input = new MemoryStream(bytes);
        var stored = await storage.SaveAsync(input);
        Assert.Equal(Convert.ToHexStringLower(SHA256.HashData(bytes)), stored.Sha256);
        Assert.Equal(bytes.Length, stored.SizeBytes);
        Assert.EndsWith(".bin", stored.ObjectKey);
        await using var output = await storage.OpenReadAsync(stored.ObjectKey);
        using var result = new MemoryStream();
        await output.CopyToAsync(result);
        Assert.Equal(bytes, result.ToArray());
        await output.DisposeAsync();
        await storage.DeleteAsync(stored.ObjectKey);
        await storage.DeleteAsync(stored.ObjectKey);
        Assert.False(File.Exists(Path.Combine(rootPath, stored.ObjectKey)));
    }

    [Theory]
    [InlineData("../private.key")]
    [InlineData("C:/private.key")]
    [InlineData("arbitrary.bin")]
    public async Task Rejects_non_generated_object_keys(string key)
    {
        var storage = CreateStorage();
        await Assert.ThrowsAsync<ArgumentException>(() => storage.OpenReadAsync(key));
        await Assert.ThrowsAsync<ArgumentException>(() => storage.DeleteAsync(key));
    }

    [Fact]
    public async Task Rejects_oversized_objects_before_persisting()
    {
        var storage = CreateStorage(2);
        using var input = new MemoryStream(new byte[3]);
        await Assert.ThrowsAsync<ArgumentException>(() => storage.SaveAsync(input));
        Assert.False(Directory.Exists(rootPath));
    }

    public void Dispose()
    {
        if (Directory.Exists(rootPath))
        {
            Directory.Delete(rootPath, recursive: true);
        }
    }
}
