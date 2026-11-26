using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace BrainSeg.EntityFrameworkCore.Migrations
{
    /// <inheritdoc />
    public partial class AddSegmentationUncertaintyArtifacts : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<bool>(
                name: "BoundaryHead",
                table: "SegmentationResults",
                type: "boolean",
                nullable: false,
                defaultValue: false);

            migrationBuilder.AddColumn<string>(
                name: "BoundaryObjectKey",
                table: "SegmentationResults",
                type: "character varying(512)",
                maxLength: 512,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "BoundarySha256",
                table: "SegmentationResults",
                type: "character varying(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "CalibrationMetricsJson",
                table: "SegmentationResults",
                type: "character varying(16384)",
                maxLength: 16384,
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "ContextSlices",
                table: "SegmentationResults",
                type: "integer",
                nullable: false,
                defaultValue: 1);

            migrationBuilder.AddColumn<bool>(
                name: "DeepSupervision",
                table: "SegmentationResults",
                type: "boolean",
                nullable: false,
                defaultValue: false);

            migrationBuilder.AddColumn<int>(
                name: "EnsembleSize",
                table: "SegmentationResults",
                type: "integer",
                nullable: false,
                defaultValue: 1);

            migrationBuilder.AddColumn<string>(
                name: "InputMode",
                table: "SegmentationResults",
                type: "character varying(8)",
                maxLength: 8,
                nullable: false,
                defaultValue: "2d");

            migrationBuilder.AddColumn<double>(
                name: "MeanUncertainty",
                table: "SegmentationResults",
                type: "double precision",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "MemberWeightHashesJson",
                table: "SegmentationResults",
                type: "character varying(1024)",
                maxLength: 1024,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "ModelVarianceObjectKey",
                table: "SegmentationResults",
                type: "character varying(512)",
                maxLength: 512,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "ModelVarianceSha256",
                table: "SegmentationResults",
                type: "character varying(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.AddColumn<double>(
                name: "P95Uncertainty",
                table: "SegmentationResults",
                type: "double precision",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "ProbabilityObjectKey",
                table: "SegmentationResults",
                type: "character varying(512)",
                maxLength: 512,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "ProbabilitySha256",
                table: "SegmentationResults",
                type: "character varying(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "SliceFusion",
                table: "SegmentationResults",
                type: "character varying(32)",
                maxLength: 32,
                nullable: false,
                defaultValue: "stack");

            migrationBuilder.AddColumn<string>(
                name: "UncertaintyMethod",
                table: "SegmentationResults",
                type: "character varying(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "UncertaintyObjectKey",
                table: "SegmentationResults",
                type: "character varying(512)",
                maxLength: 512,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "UncertaintyRetentionMetricsJson",
                table: "SegmentationResults",
                type: "character varying(16384)",
                maxLength: 16384,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "UncertaintySha256",
                table: "SegmentationResults",
                type: "character varying(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.AddCheckConstraint(
                name: "CK_SegmentationResults_ModelShape",
                table: "SegmentationResults",
                sql: "\"InputMode\" IN ('2d', '2p5d') AND \"ContextSlices\" BETWEEN 1 AND 9 AND \"ContextSlices\" % 2 = 1 AND \"SliceFusion\" IN ('stack', 'center_attention') AND \"EnsembleSize\" >= 1");

            migrationBuilder.AddCheckConstraint(
                name: "CK_SegmentationResults_Uncertainty",
                table: "SegmentationResults",
                sql: "(\"MeanUncertainty\" IS NULL OR \"MeanUncertainty\" BETWEEN 0 AND 100) AND (\"P95Uncertainty\" IS NULL OR \"P95Uncertainty\" BETWEEN 0 AND 100)");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropCheckConstraint(
                name: "CK_SegmentationResults_ModelShape",
                table: "SegmentationResults");

            migrationBuilder.DropCheckConstraint(
                name: "CK_SegmentationResults_Uncertainty",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "BoundaryHead",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "BoundaryObjectKey",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "BoundarySha256",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "CalibrationMetricsJson",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "ContextSlices",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "DeepSupervision",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "EnsembleSize",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "InputMode",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "MeanUncertainty",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "MemberWeightHashesJson",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "ModelVarianceObjectKey",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "ModelVarianceSha256",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "P95Uncertainty",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "ProbabilityObjectKey",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "ProbabilitySha256",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "SliceFusion",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "UncertaintyMethod",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "UncertaintyObjectKey",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "UncertaintyRetentionMetricsJson",
                table: "SegmentationResults");

            migrationBuilder.DropColumn(
                name: "UncertaintySha256",
                table: "SegmentationResults");
        }
    }
}
