#!/usr/bin/env pwsh
# Sign in and create or update the Fabric IQ UserEntraToken connection.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = if ($env:ENV_FILE) { $env:ENV_FILE } else { Join-Path $scriptDir ".env" }

if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw "Cannot read environment file: $envFile"
}

$envNames = @(
    "TENANT_ID",
    "SUBSCRIPTION_ID",
    "AZURE_AI_PROJECT_ID",
    "FABRIC_IQ_CONNECTION_NAME",
    "FABRIC_IQ_SERVER_URL",
    "FABRIC_IQ_ITEM_TYPE",
    "FABRIC_WORKSPACE_ID",
    "FABRIC_ARTIFACT_ID"
)

$existingOverrides = @{}
foreach ($name in $envNames) {
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    if ($null -ne $value -and $value -ne "") {
        $existingOverrides[$name] = $value
    }
}

foreach ($line in Get-Content -LiteralPath $envFile) {
    $trimmed = $line.Trim()
    if ($trimmed -eq "" -or $trimmed.StartsWith("#")) {
        continue
    }

    $separator = $trimmed.IndexOf("=")
    if ($separator -lt 1) {
        continue
    }

    $name = $trimmed.Substring(0, $separator).Trim()
    $value = $trimmed.Substring($separator + 1).Trim()
    if ($value.Length -ge 2) {
        $first = $value[0]
        $last = $value[$value.Length - 1]
        if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
            $value = $value.Substring(1, $value.Length - 2)
        }
    }

    [Environment]::SetEnvironmentVariable($name, $value, "Process")
}

foreach ($name in $existingOverrides.Keys) {
    [Environment]::SetEnvironmentVariable(
        $name,
        $existingOverrides[$name],
        "Process"
    )
}

foreach ($name in @("TENANT_ID", "AZURE_AI_PROJECT_ID", "FABRIC_IQ_CONNECTION_NAME")) {
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "$name is required"
    }
}

$tenantId = $env:TENANT_ID
$projectId = $env:AZURE_AI_PROJECT_ID.TrimEnd("/")
$connectionName = $env:FABRIC_IQ_CONNECTION_NAME
$subscriptionId = $env:SUBSCRIPTION_ID
if ([string]::IsNullOrWhiteSpace($subscriptionId)) {
    if ($projectId -notmatch "^/subscriptions/([^/]+)/") {
        throw "Could not derive subscription ID from AZURE_AI_PROJECT_ID"
    }
    $subscriptionId = $Matches[1]
}

$fabricHost = "https://api.fabric.microsoft.com"
$target = $env:FABRIC_IQ_SERVER_URL

if ([string]::IsNullOrWhiteSpace($target)) {
    $itemType = if ($env:FABRIC_IQ_ITEM_TYPE) {
        $env:FABRIC_IQ_ITEM_TYPE.Trim().ToLowerInvariant().Replace("_", "-")
    } else {
        "dataagent"
    }

    switch ($itemType) {
        "ontology" {
            foreach ($name in @("FABRIC_WORKSPACE_ID", "FABRIC_ARTIFACT_ID")) {
                if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, "Process"))) {
                    throw "$name is required"
                }
            }
            $target = "$fabricHost/v1/mcp/dataPlane/workspaces/$env:FABRIC_WORKSPACE_ID/items/$env:FABRIC_ARTIFACT_ID/ontologyEndpoint"
        }
        "dataagent" {
            foreach ($name in @("FABRIC_WORKSPACE_ID", "FABRIC_ARTIFACT_ID")) {
                if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, "Process"))) {
                    throw "$name is required"
                }
            }
            $target = "$fabricHost/v1/mcp/workspaces/$env:FABRIC_WORKSPACE_ID/dataagents/$env:FABRIC_ARTIFACT_ID/agent"
        }
        "data-agent" {
            foreach ($name in @("FABRIC_WORKSPACE_ID", "FABRIC_ARTIFACT_ID")) {
                if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, "Process"))) {
                    throw "$name is required"
                }
            }
            $target = "$fabricHost/v1/mcp/workspaces/$env:FABRIC_WORKSPACE_ID/dataagents/$env:FABRIC_ARTIFACT_ID/agent"
        }
        "semanticmodel" {
            $target = "$fabricHost/v1/mcp/fabricaihub/integrations/m365"
        }
        "semantic-model" {
            $target = "$fabricHost/v1/mcp/fabricaihub/integrations/m365"
        }
        "powerbi" {
            $target = "$fabricHost/v1/mcp/fabricaihub/integrations/m365"
        }
        "pbi" {
            $target = "$fabricHost/v1/mcp/fabricaihub/integrations/m365"
        }
        default {
            throw "Unrecognized FABRIC_IQ_ITEM_TYPE: $itemType"
        }
    }
}

$url = "https://management.azure.com$projectId/connections/$connectionName" +
    "?api-version=2025-10-01-preview"

& az login --tenant $tenantId --output none
if ($LASTEXITCODE -ne 0) {
    throw "Azure CLI login failed"
}

$body = @{
    properties = @{
        category = "RemoteTool"
        authType = "UserEntraToken"
        target = $target
        audience = $fabricHost
        metadata = @{ type = "fabric_iq_preview" }
        isSharedToAll = $false
    }
}

$bodyFile = [System.IO.Path]::GetTempFileName()

try {
    $body | ConvertTo-Json -Depth 10 |
        Set-Content -LiteralPath $bodyFile -Encoding utf8

    & az rest `
        --subscription $subscriptionId `
        --method put `
        --url $url `
        --headers "Content-Type=application/json" `
        --body "@$bodyFile" `
        --output none

    if ($LASTEXITCODE -ne 0) {
        throw "Azure REST connection update failed"
    }

    Write-Host "Connection created or updated: $connectionName"
}
finally {
    Remove-Item -LiteralPath $bodyFile -Force -ErrorAction SilentlyContinue
}
