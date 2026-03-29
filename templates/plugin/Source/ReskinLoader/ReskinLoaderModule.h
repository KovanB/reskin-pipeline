#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"

class FReskinLoaderModule : public IModuleInterface
{
public:
    virtual void StartupModule() override;
    virtual void ShutdownModule() override;

private:
    void LoadRedirectMap();
    void ApplyRedirects();

    TMap<FString, FString> RedirectMap;
};
