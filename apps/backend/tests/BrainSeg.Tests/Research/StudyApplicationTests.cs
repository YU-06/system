using System.Buffers.Binary;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using BrainSeg.Research;
using Microsoft.Extensions.DependencyInjection;
using Volo.Abp.Auditing;
using Volo.Abp.Domain.Repositories;
using Xunit;

namespace BrainSeg.Tests.Research;

public class StudyApplicationTests
{
    internal static byte[] NiftiBytes()
    {
        var bytes = new byte[352 + 8 * 8 * 2 * 4];
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(0), 348);
        BinaryPrimitives.WriteInt16LittleEndian(bytes.AsSpan(40), 3);
        BinaryPrimitives.WriteInt16LittleEndian(bytes.AsSpan(42), 8);
        BinaryPrimitives.WriteInt16LittleEndian(bytes.AsSpan(44), 8);
        BinaryPrimitives.WriteInt16LittleEndian(bytes.AsSpan(46), 2);
        BinaryPrimitives.WriteInt16LittleEndian(bytes.AsSpan(70), 16);
        BinaryPrimitives.WriteInt16LittleEndian(bytes.AsSpan(72), 32);
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(108), BitConverter.SingleToInt32Bits(352));
        "n+1\0"u8.CopyTo(bytes.AsSpan(344));
        return bytes;
    }

    private static MultipartFormDataContent Upload(string number, byte[] bytes, string name = "synthetic.nii")
    {
        var form = new MultipartFormDataContent();
        form.Add(new StringContent(number), "StudyNumber");
        form.Add(new StringContent("case_001"), "Pseudonym");
        form.Add(new StringContent("0"), "SliceIndex");
        var file = new ByteArrayContent(bytes);
        file.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        form.Add(file, "File", name);
        return form;
    }

    [Fact]
    public async Task Multipart_upload_stores_only_metadata_and_rejects_stale_updates()
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        using var client = factory.AuthenticatedClient(ResearchPermissions.BrainStudies.Default,
            ResearchPermissions.BrainStudies.Create, ResearchPermissions.BrainStudies.Update);
        var bytes = NiftiBytes();
        using var form = Upload("study-http-1", bytes);
        using var uploaded = await client.PostAsync("/api/app/brain-study/upload", form);
        Assert.True(uploaded.IsSuccessStatusCode, await uploaded.Content.ReadAsStringAsync());
        var study = (await uploaded.Content.ReadFromJsonAsync<BrainStudyDto>())!;
        Assert.Equal(8, study.Width);
        Assert.Equal(BrainStudyStatus.Ready, study.Status);
        Assert.Equal(ResearchFactory.UserId, study.CreatorId);
        Assert.Equal(Convert.ToHexStringLower(SHA256.HashData(bytes)), study.OriginalFileSha256);
        Assert.EndsWith(".bin", study.OriginalFileObjectKey);
        Assert.DoesNotContain("synthetic", study.OriginalFileObjectKey);
        using var update = await client.PutAsJsonAsync($"/api/app/brain-study/{study.Id}",
            new UpdateBrainStudyInput { Pseudonym = "case_002", ConcurrencyStamp = study.ConcurrencyStamp });
        Assert.True(update.IsSuccessStatusCode, await update.Content.ReadAsStringAsync());
        using var stale = await client.PutAsJsonAsync($"/api/app/brain-study/{study.Id}",
            new UpdateBrainStudyInput { Pseudonym = "case_003", ConcurrencyStamp = study.ConcurrencyStamp });
        Assert.Equal(HttpStatusCode.Conflict, stale.StatusCode);
        var audit = (ResearchTestAuditingStore)factory.Services.GetRequiredService<IAuditingStore>();
        var actions = audit.Entries.SelectMany(entry => entry.Actions)
            .Where(action => action.MethodName == nameof(IBrainStudyAppService.UploadAsync)).ToArray();
        Assert.NotEmpty(actions);
        Assert.All(actions, action =>
        {
            Assert.DoesNotContain("synthetic.nii", action.Parameters);
            Assert.DoesNotContain(Convert.ToBase64String(bytes), action.Parameters);
        });
    }

    [Theory]
    [InlineData("type")]
    [InlineData("header")]
    [InlineData("truncated")]
    [InlineData("gzip")]
    public async Task Invalid_uploads_are_rejected_without_creating_studies(string scenario)
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        using var client = factory.AuthenticatedClient(ResearchPermissions.BrainStudies.Default, ResearchPermissions.BrainStudies.Create);
        var bytes = scenario switch
        {
            "header" or "gzip" => "invalid"u8.ToArray(),
            "truncated" => NiftiBytes()[..352],
            _ => NiftiBytes()
        };
        var name = scenario switch { "type" => "fixture.txt", "gzip" => "fixture.nii.gz", _ => "fixture.nii" };
        using var form = Upload("invalid-input", bytes, name);
        using var response = await client.PostAsync("/api/app/brain-study/upload", form);
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Contains(ResearchErrors.InvalidFile, await response.Content.ReadAsStringAsync());
        await factory.RunAsync(async services => Assert.Equal(0,
            await services.GetRequiredService<IBrainStudyRepository>().GetCountAsync()));
    }

    [Fact]
    public async Task Anonymous_and_read_only_users_cannot_write()
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        using var anonymous = factory.CreateClient();
        using var denied = await anonymous.GetAsync("/api/app/brain-study");
        Assert.Equal(HttpStatusCode.Unauthorized, denied.StatusCode);
        using var reader = factory.AuthenticatedClient(ResearchPermissions.BrainStudies.Default);
        using var form = Upload("not-allowed", NiftiBytes());
        using var forbidden = await reader.PostAsync("/api/app/brain-study/upload", form);
        Assert.Equal(HttpStatusCode.Forbidden, forbidden.StatusCode);
    }

    [Fact]
    public async Task Lists_filter_page_and_sort_only_allowlisted_fields()
    {
        using var factory = new ResearchFactory();
        await factory.InitializeAsync();
        await factory.RunAsync(async services =>
        {
            var repository = services.GetRequiredService<IBrainStudyRepository>();
            for (var index = 0; index < 3; index++)
            {
                var study = new BrainStudy(Guid.NewGuid(), $"PAGE-{index}", $"case_{index}", AggregateTests.ObjectKey(),
                    new string((char)('a' + index), 64), 8, 8, 0);
                study.MarkReady();
                await repository.InsertAsync(study, autoSave: true);
            }
        });
        using var client = factory.AuthenticatedClient(ResearchPermissions.BrainStudies.Default);
        var response = await client.GetFromJsonAsync<Volo.Abp.Application.Dtos.PagedResultDto<BrainStudyDto>>(
            "/api/app/brain-study?filter=page&sorting=studyNumber%20desc&skipCount=1&maxResultCount=1");
        Assert.Equal(3, response!.TotalCount);
        Assert.Equal("PAGE-1", Assert.Single(response.Items).StudyNumber);
        using var invalidSort = await client.GetAsync("/api/app/brain-study?sorting=StudyNumber.ToString()");
        Assert.False(invalidSort.IsSuccessStatusCode);
        Assert.Contains(ResearchErrors.InvalidSorting, await invalidSort.Content.ReadAsStringAsync());
    }
}
