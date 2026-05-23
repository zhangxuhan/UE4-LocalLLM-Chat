// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class ProjectChat : ModuleRules
{
	public ProjectChat(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "HeadMountedDisplay", "Http", "Json", "JsonUtilities", "UnLua" });
	}
}
