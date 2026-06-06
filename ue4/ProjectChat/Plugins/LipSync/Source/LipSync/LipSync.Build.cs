// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class LipSync : ModuleRules
{
    public LipSync(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "Http",
            "Json",
            "JsonUtilities",
            "AudioMixer",   // TTSLipSyncComponent 播放音频用
        });

        PrivateDependencyModuleNames.AddRange(new string[]
        {
            "InputCore",
        });
    }
}
