using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace BrainSeg.EntityFrameworkCore.Migrations
{
    /// <inheritdoc />
    public partial class AddResearchDomain : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "BrainStudies",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    StudyNumber = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Pseudonym = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Modality = table.Column<string>(type: "character varying(16)", maxLength: 16, nullable: false),
                    OriginalFileObjectKey = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: false),
                    OriginalFileSha256 = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Width = table.Column<int>(type: "integer", nullable: false),
                    Height = table.Column<int>(type: "integer", nullable: false),
                    SliceIndex = table.Column<int>(type: "integer", nullable: false),
                    Status = table.Column<int>(type: "integer", nullable: false),
                    JobRequestCount = table.Column<int>(type: "integer", nullable: false),
                    ExtraProperties = table.Column<string>(type: "text", nullable: false),
                    ConcurrencyStamp = table.Column<string>(type: "character varying(40)", maxLength: 40, nullable: false),
                    CreationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    CreatorId = table.Column<Guid>(type: "uuid", nullable: true),
                    LastModificationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    LastModifierId = table.Column<Guid>(type: "uuid", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    DeleterId = table.Column<Guid>(type: "uuid", nullable: true),
                    DeletionTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_BrainStudies", x => x.Id);
                    table.CheckConstraint("CK_BrainStudies_Dimensions", "\"Width\" BETWEEN 1 AND 512 AND \"Height\" BETWEEN 1 AND 512 AND \"SliceIndex\" BETWEEN 0 AND 511 AND \"JobRequestCount\" >= 0");
                });

            migrationBuilder.CreateTable(
                name: "ModelVersions",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Name = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    NormalizedName = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    Architecture = table.Column<int>(type: "integer", nullable: false),
                    SemanticVersion = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    PreprocessingVersion = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    WeightObjectKey = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: false),
                    WeightSha256 = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    InputSize = table.Column<int>(type: "integer", nullable: false),
                    Threshold = table.Column<double>(type: "double precision", nullable: false),
                    MetricsJson = table.Column<string>(type: "character varying(16384)", maxLength: 16384, nullable: false),
                    IsActive = table.Column<bool>(type: "boolean", nullable: false),
                    IsDefault = table.Column<bool>(type: "boolean", nullable: false),
                    PublishedTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    ExtraProperties = table.Column<string>(type: "text", nullable: false),
                    ConcurrencyStamp = table.Column<string>(type: "character varying(40)", maxLength: 40, nullable: false),
                    CreationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    CreatorId = table.Column<Guid>(type: "uuid", nullable: true),
                    LastModificationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    LastModifierId = table.Column<Guid>(type: "uuid", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    DeleterId = table.Column<Guid>(type: "uuid", nullable: true),
                    DeletionTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ModelVersions", x => x.Id);
                    table.CheckConstraint("CK_ModelVersions_Default", "\"IsDefault\" = false OR \"IsActive\" = true");
                    table.CheckConstraint("CK_ModelVersions_Protocol", "\"InputSize\" = 256 AND \"Threshold\" > 0 AND \"Threshold\" < 1");
                });

            migrationBuilder.CreateTable(
                name: "ExperimentRuns",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    ExperimentName = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    ConfigHash = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    GitCommit = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    DatasetSplitHash = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    RandomSeed = table.Column<int>(type: "integer", nullable: false),
                    ModelVersionId = table.Column<Guid>(type: "uuid", nullable: false),
                    MetricsJson = table.Column<string>(type: "character varying(16384)", maxLength: 16384, nullable: false),
                    ArtifactObjectKey = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: false),
                    CreatedTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    ExtraProperties = table.Column<string>(type: "text", nullable: false),
                    ConcurrencyStamp = table.Column<string>(type: "character varying(40)", maxLength: 40, nullable: false),
                    CreationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    CreatorId = table.Column<Guid>(type: "uuid", nullable: true),
                    LastModificationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    LastModifierId = table.Column<Guid>(type: "uuid", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    DeleterId = table.Column<Guid>(type: "uuid", nullable: true),
                    DeletionTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ExperimentRuns", x => x.Id);
                    table.CheckConstraint("CK_ExperimentRuns_Seed", "\"RandomSeed\" >= 0");
                    table.ForeignKey(
                        name: "FK_ExperimentRuns_ModelVersions_ModelVersionId",
                        column: x => x.ModelVersionId,
                        principalTable: "ModelVersions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "SegmentationJobs",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    StudyId = table.Column<Guid>(type: "uuid", nullable: false),
                    ModelVersionId = table.Column<Guid>(type: "uuid", nullable: false),
                    RequesterId = table.Column<Guid>(type: "uuid", nullable: false),
                    IdempotencyKey = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    Status = table.Column<int>(type: "integer", nullable: false),
                    Progress = table.Column<int>(type: "integer", nullable: false),
                    CorrelationId = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    RequestedTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    StartedTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    CompletedTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    ErrorCode = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: true),
                    ErrorMessage = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    RetryCount = table.Column<int>(type: "integer", nullable: false),
                    ExtraProperties = table.Column<string>(type: "text", nullable: false),
                    ConcurrencyStamp = table.Column<string>(type: "character varying(40)", maxLength: 40, nullable: false),
                    CreationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    CreatorId = table.Column<Guid>(type: "uuid", nullable: true),
                    LastModificationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    LastModifierId = table.Column<Guid>(type: "uuid", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    DeleterId = table.Column<Guid>(type: "uuid", nullable: true),
                    DeletionTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SegmentationJobs", x => x.Id);
                    table.CheckConstraint("CK_SegmentationJobs_Progress", "\"Progress\" BETWEEN 0 AND 100");
                    table.CheckConstraint("CK_SegmentationJobs_RetryCount", "\"RetryCount\" BETWEEN 0 AND 3");
                    table.ForeignKey(
                        name: "FK_SegmentationJobs_BrainStudies_StudyId",
                        column: x => x.StudyId,
                        principalTable: "BrainStudies",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_SegmentationJobs_ModelVersions_ModelVersionId",
                        column: x => x.ModelVersionId,
                        principalTable: "ModelVersions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "SegmentationResults",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    JobId = table.Column<Guid>(type: "uuid", nullable: false),
                    MaskObjectKey = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: false),
                    OverlayObjectKey = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: false),
                    ContourObjectKey = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: false),
                    Dice = table.Column<double>(type: "double precision", nullable: true),
                    IoU = table.Column<double>(type: "double precision", nullable: true),
                    Precision = table.Column<double>(type: "double precision", nullable: true),
                    Recall = table.Column<double>(type: "double precision", nullable: true),
                    TumorAreaPixels = table.Column<int>(type: "integer", nullable: false),
                    TumorAreaRatio = table.Column<double>(type: "double precision", nullable: false),
                    InferenceMilliseconds = table.Column<double>(type: "double precision", nullable: false),
                    PreprocessingMilliseconds = table.Column<double>(type: "double precision", nullable: false),
                    PostprocessingMilliseconds = table.Column<double>(type: "double precision", nullable: false),
                    CreatedTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    ExtraProperties = table.Column<string>(type: "text", nullable: false),
                    ConcurrencyStamp = table.Column<string>(type: "character varying(40)", maxLength: 40, nullable: false),
                    CreationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    CreatorId = table.Column<Guid>(type: "uuid", nullable: true),
                    LastModificationTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    LastModifierId = table.Column<Guid>(type: "uuid", nullable: true),
                    IsDeleted = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    DeleterId = table.Column<Guid>(type: "uuid", nullable: true),
                    DeletionTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_SegmentationResults", x => x.Id);
                    table.CheckConstraint("CK_SegmentationResults_Area", "\"TumorAreaPixels\" BETWEEN 0 AND 65536 AND \"TumorAreaRatio\" BETWEEN 0 AND 1");
                    table.CheckConstraint("CK_SegmentationResults_Metrics", "(\"Dice\" IS NULL OR \"Dice\" BETWEEN 0 AND 1) AND (\"IoU\" IS NULL OR \"IoU\" BETWEEN 0 AND 1) AND (\"Precision\" IS NULL OR \"Precision\" BETWEEN 0 AND 1) AND (\"Recall\" IS NULL OR \"Recall\" BETWEEN 0 AND 1)");
                    table.CheckConstraint("CK_SegmentationResults_Timings", "\"InferenceMilliseconds\" >= 0 AND \"PreprocessingMilliseconds\" >= 0 AND \"PostprocessingMilliseconds\" >= 0");
                    table.ForeignKey(
                        name: "FK_SegmentationResults_SegmentationJobs_JobId",
                        column: x => x.JobId,
                        principalTable: "SegmentationJobs",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_BrainStudies_Status_CreationTime",
                table: "BrainStudies",
                columns: new[] { "Status", "CreationTime" });

            migrationBuilder.CreateIndex(
                name: "UX_BrainStudies_FileSlice",
                table: "BrainStudies",
                columns: new[] { "OriginalFileSha256", "SliceIndex" },
                unique: true,
                filter: "\"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "UX_BrainStudies_Number",
                table: "BrainStudies",
                column: "StudyNumber",
                unique: true,
                filter: "\"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "IX_ExperimentRuns_CreatedTime",
                table: "ExperimentRuns",
                column: "CreatedTime");

            migrationBuilder.CreateIndex(
                name: "IX_ExperimentRuns_ModelVersionId",
                table: "ExperimentRuns",
                column: "ModelVersionId");

            migrationBuilder.CreateIndex(
                name: "UX_ExperimentRuns_Reproducibility",
                table: "ExperimentRuns",
                columns: new[] { "ExperimentName", "ConfigHash", "DatasetSplitHash", "GitCommit", "RandomSeed", "ModelVersionId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_ModelVersions_IsActive_Architecture",
                table: "ModelVersions",
                columns: new[] { "IsActive", "Architecture" });

            migrationBuilder.CreateIndex(
                name: "UX_ModelVersions_Default",
                table: "ModelVersions",
                column: "IsDefault",
                unique: true,
                filter: "\"IsDefault\" = true AND \"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "UX_ModelVersions_Identity",
                table: "ModelVersions",
                columns: new[] { "Architecture", "NormalizedName", "SemanticVersion" },
                unique: true,
                filter: "\"IsDeleted\" = false");

            migrationBuilder.CreateIndex(
                name: "IX_SegmentationJobs_ModelVersionId",
                table: "SegmentationJobs",
                column: "ModelVersionId");

            migrationBuilder.CreateIndex(
                name: "IX_SegmentationJobs_Status_RequestedTime",
                table: "SegmentationJobs",
                columns: new[] { "Status", "RequestedTime" });

            migrationBuilder.CreateIndex(
                name: "IX_SegmentationJobs_StudyId_Status",
                table: "SegmentationJobs",
                columns: new[] { "StudyId", "Status" });

            migrationBuilder.CreateIndex(
                name: "UX_SegmentationJobs_Idempotency",
                table: "SegmentationJobs",
                columns: new[] { "RequesterId", "IdempotencyKey" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_SegmentationResults_CreatedTime",
                table: "SegmentationResults",
                column: "CreatedTime");

            migrationBuilder.CreateIndex(
                name: "UX_SegmentationResults_Job",
                table: "SegmentationResults",
                column: "JobId",
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "ExperimentRuns");

            migrationBuilder.DropTable(
                name: "SegmentationResults");

            migrationBuilder.DropTable(
                name: "SegmentationJobs");

            migrationBuilder.DropTable(
                name: "BrainStudies");

            migrationBuilder.DropTable(
                name: "ModelVersions");
        }
    }
}
