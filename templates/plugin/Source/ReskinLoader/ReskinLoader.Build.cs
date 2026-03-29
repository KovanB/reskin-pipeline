using UnrealBuildTool;

public class ReskinLoader : ModuleRules
{
    public ReskinLoader(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core",
            "CoreUObject",
            "Engine",
        });

        PrivateDependencyModuleNames.AddRange(new string[]
        {
            "Json",
            "JsonUtilities",
        });
    }
}
