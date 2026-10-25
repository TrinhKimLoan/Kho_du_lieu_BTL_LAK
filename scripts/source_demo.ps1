param(
    [ValidateSet('insert','update','delete','status')]
    [string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.runtime/lak.env'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'Run scripts/run_phase3.ps1 first.' }
$composeFile = Join-Path $root 'infra/compose.lak.yaml'
$savedPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    & docker compose --project-name lak-analytics --env-file $envFile -f $composeFile run --rm source-tools demo --action $Action
    $nativeCode = $LASTEXITCODE
} finally { $ErrorActionPreference = $savedPreference }
if ($nativeCode -ne 0) { exit $nativeCode }
