using Volo.Abp.Authorization.Permissions;
using Volo.Abp.Localization;

namespace BrainSeg.Research;

public static class ResearchPermissions
{
    public const string GroupName = "BrainSeg";

    public static class BrainStudies
    {
        public const string Default = "BrainSeg.BrainStudies";
        public const string Create = Default + ".Create";
        public const string Update = Default + ".Update";
        public const string Delete = Default + ".Delete";
    }

    public static class SegmentationJobs
    {
        public const string Default = "BrainSeg.SegmentationJobs";
        public const string Create = Default + ".Create";
        public const string Execute = Default + ".Execute";
        public const string Cancel = Default + ".Cancel";
        public const string Retry = Default + ".Retry";
    }

    public static class ModelVersions
    {
        public const string Default = "BrainSeg.ModelVersions";
        public const string Create = Default + ".Create";
        public const string Manage = Default + ".Manage";
    }

    public static class SegmentationResults
    {
        public const string Default = "BrainSeg.SegmentationResults";
    }

    public static class ExperimentRuns
    {
        public const string Default = "BrainSeg.ExperimentRuns";
        public const string Create = Default + ".Create";
    }
}

public class ResearchPermissionDefinitionProvider : PermissionDefinitionProvider
{
    public override void Define(IPermissionDefinitionContext context)
    {
        var group = context.AddGroup(ResearchPermissions.GroupName, LocalizableString.Create<BrainSegResource>("Permission:Research"));
        Add(group, ResearchPermissions.BrainStudies.Default, "BrainStudies", "Create", "Update", "Delete");
        Add(group, ResearchPermissions.SegmentationJobs.Default, "SegmentationJobs", "Create", "Execute", "Cancel", "Retry");
        Add(group, ResearchPermissions.ModelVersions.Default, "ModelVersions", "Create", "Manage");
        Add(group, ResearchPermissions.SegmentationResults.Default, "SegmentationResults");
        Add(group, ResearchPermissions.ExperimentRuns.Default, "ExperimentRuns", "Create");
    }

    private static void Add(PermissionGroupDefinition group, string name, string resource, params string[] children)
    {
        var permission = group.AddPermission(name, LocalizableString.Create<BrainSegResource>($"Permission:{resource}"));
        foreach (var child in children)
        {
            permission.AddChild($"{name}.{child}", LocalizableString.Create<BrainSegResource>($"Permission:{resource}.{child}"));
        }
    }
}
