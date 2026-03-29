#include "ReskinLoaderModule.h"
#include "CoreRedirects.h"
#include "Dom/JsonObject.h"
#include "HAL/PlatformFilemanager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

#define LOCTEXT_NAMESPACE "FReskinLoaderModule"

IMPLEMENT_MODULE(FReskinLoaderModule, ReskinLoader)

void FReskinLoaderModule::StartupModule()
{
    UE_LOG(LogTemp, Log, TEXT("ReskinLoader: Starting up — ${skin_name}"));
    LoadRedirectMap();
    ApplyRedirects();
}

void FReskinLoaderModule::ShutdownModule()
{
    UE_LOG(LogTemp, Log, TEXT("ReskinLoader: Shutting down"));
}

void FReskinLoaderModule::LoadRedirectMap()
{
    // Load redirect_map.json from plugin's Config directory
    FString PluginDir = FPaths::Combine(
        FPaths::ProjectPluginsDir(),
        TEXT("${plugin_name}"),
        TEXT("Config"),
        TEXT("redirect_map.json")
    );

    FString JsonString;
    if (!FFileHelper::LoadFileToString(JsonString, *PluginDir))
    {
        UE_LOG(LogTemp, Warning, TEXT("ReskinLoader: Could not load redirect map at %s"), *PluginDir);
        return;
    }

    TSharedPtr<FJsonObject> JsonObject;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonString);

    if (!FJsonSerializer::Deserialize(Reader, JsonObject) || !JsonObject.IsValid())
    {
        UE_LOG(LogTemp, Error, TEXT("ReskinLoader: Failed to parse redirect map JSON"));
        return;
    }

    for (const auto& Pair : JsonObject->Values)
    {
        FString Value;
        if (Pair.Value->TryGetString(Value))
        {
            RedirectMap.Add(Pair.Key, Value);
        }
    }

    UE_LOG(LogTemp, Log, TEXT("ReskinLoader: Loaded %d asset redirects"), RedirectMap.Num());
}

void FReskinLoaderModule::ApplyRedirects()
{
    // Register core redirects so the engine transparently loads our reskinned textures
    // instead of the originals
    TArray<FCoreRedirect> Redirects;

    for (const auto& Pair : RedirectMap)
    {
        FCoreRedirect Redirect(
            ECoreRedirectFlags::Type_Asset,
            FCoreRedirectObjectName(Pair.Key),
            FCoreRedirectObjectName(Pair.Value)
        );
        Redirects.Add(Redirect);
    }

    FCoreRedirects::AddRedirectList(Redirects, TEXT("ReskinLoader"));
    UE_LOG(LogTemp, Log, TEXT("ReskinLoader: Applied %d asset redirects"), Redirects.Num());
}

#undef LOCTEXT_NAMESPACE
