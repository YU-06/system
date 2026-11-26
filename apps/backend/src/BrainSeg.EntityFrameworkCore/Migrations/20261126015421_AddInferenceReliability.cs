using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace BrainSeg.EntityFrameworkCore.Migrations
{
    /// <inheritdoc />
    public partial class AddInferenceReliability : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AlterColumn<string>(
                name: "OverlayObjectKey",
                table: "SegmentationResults",
                type: "character varying(512)",
                maxLength: 512,
                nullable: true,
                oldClrType: typeof(string),
                oldType: "character varying(512)",
                oldMaxLength: 512);

            migrationBuilder.AlterColumn<string>(
                name: "ContourObjectKey",
                table: "SegmentationResults",
                type: "character varying(512)",
                maxLength: 512,
                nullable: true,
                oldClrType: typeof(string),
                oldType: "character varying(512)",
                oldMaxLength: 512);

            migrationBuilder.AddColumn<string>(
                name: "EvaluationProtocol",
                table: "SegmentationResults",
                type: "character varying(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "GroundTruthSha256",
                table: "SegmentationResults",
                type: "character varying(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "MaskSha256",
                table: "SegmentationResults",
                type: "character varying(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "RemotePredictionObjectKey",
                table: "SegmentationResults",
                type: "character varying(512)",
                maxLength: 512,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "RemotePredictionSha256",
                table: "SegmentationResults",
                type: "character varying(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "Architecture",
                table: "SegmentationJobs",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<Guid>(
                name: "ClaimToken",
                table: "SegmentationJobs",
                type: "uuid",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "InputSha256",
                table: "SegmentationJobs",
                type: "character varying(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "InputSize",
                table: "SegmentationJobs",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<DateTime>(
                name: "LeaseExpiresAt",
                table: "SegmentationJobs",
                type: "timestamp with time zone",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "ModelSemanticVersion",
                table: "SegmentationJobs",
                type: "character varying(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "PreprocessingVersion",
                table: "SegmentationJobs",
                type: "character varying(32)",
                maxLength: 32,
                nullable: true);

            migrationBuilder.AddColumn<double>(
                name: "Threshold",
                table: "SegmentationJobs",
                type: "double precision",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "WeightSha256",
                table: "SegmentationJobs",
                type: "character varying(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "GroundTruthObjectKey",
                table: "BrainStudies",
                type: "character varying(512)",
                maxLength: 512,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "GroundTruthSha256",
                table: "BrainStudies",
                type: "character varying(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.CreateTable(
                name: "ObjectWriteIntents",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    ObjectKey = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: false),
                    Purpose = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    RequestedTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    NextAttemptTime = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    AttemptCount = table.Column<int>(type: "integer", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ObjectWriteIntents", x => x.Id);
                    table.CheckConstraint("CK_ObjectWriteIntents_AttemptCount", "\"AttemptCount\" >= 0");
                });

            migrationBuilder.CreateIndex(
                name: "IX_SegmentationJobs_Status_LeaseExpiresAt",
                table: "SegmentationJobs",
                columns: new[] { "Status", "LeaseExpiresAt" });

            migrationBuilder.CreateIndex(
                name: "IX_ObjectWriteIntents_NextAttemptTime",
                table: "ObjectWriteIntents",
                column: "NextAttemptTime");

            migrationBuilder.CreateIndex(
                name: "UX_ObjectWriteIntents_ObjectKey",
                table: "ObjectWriteIntents",
                column: "ObjectKey",
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "ObjectWriteIntents");

            migrationBuilder.DropIndex(
                name: "IX_SegmentationJobs_Status_LeaseExpiresAt",
                table: "SegmentationJobs");

            migrationBuilder.DropColumn(
                name: "EvaluationProtocol",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "GroundTruthSha256",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "MaskSha256",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "RemotePredictionObjectKey",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "RemotePredictionSha256",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "Architecture",
                table: "SegmentationJobs");

            migrationBuilder.DropColumn(
                name: "ClaimToken",
                table: "SegmentationJobs");

            migrationBuilder.DropColumn(
                name: "InputSha256",
                table: "SegmentationJobs");

            migrationBuilder.DropColumn(
                name: "InputSize",
                table: "SegmentationJobs");

            migrationBuilder.DropColumn(
                name: "LeaseExpiresAt",
                table: "SegmentationJobs");

            migrationBuilder.DropColumn(
                name: "ModelSemanticVersion",
                table: "SegmentationJobs");

            migrationBuilder.DropColumn(
                name: "PreprocessingVersion",
                table: "SegmentationJobs");

            migrationBuilder.DropColumn(
                name: "Threshold",
                table: "SegmentationJobs");

            migrationBuilder.DropColumn(
                name: "WeightSha256",
                table: "SegmentationJobs");

            migrationBuilder.DropColumn(
                name: "GroundTruthObjectKey",
                table: "BrainStudies");

            migrationBuilder.DropColumn(
                name: "GroundTruthSha256",
                table: "BrainStudies");

            migrationBuilder.AlterColumn<string>(
                name: "OverlayObjectKey",
                table: "SegmentationResults",
                type: "character varying(512)",
                maxLength: 512,
                nullable: false,
                defaultValue: "",
                oldClrType: typeof(string),
                oldType: "character varying(512)",
                oldMaxLength: 512,
                oldNullable: true);

            migrationBuilder.AlterColumn<string>(
                name: "ContourObjectKey",
                table: "SegmentationResults",
                type: "character varying(512)",
                maxLength: 512,
                nullable: false,
                defaultValue: "",
                oldClrType: typeof(string),
                oldType: "character varying(512)",
                oldMaxLength: 512,
                oldNullable: true);
        }
    }
}
