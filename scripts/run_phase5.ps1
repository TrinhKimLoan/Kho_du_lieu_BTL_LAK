$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$envFile = Join-Path $root '.runtime/lak.env'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'Existing phase 4 credentials are required.' }
$compose = @('compose','--project-name','lak-analytics','--env-file',$envFile,'-f',(Join-Path $root 'infra/compose.lak.yaml'))
$runName = 'run-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$evidence = Join-Path $root "evidence/phase5/$runName"
New-Item -ItemType Directory -Path $evidence | Out-Null
$log = Join-Path $evidence 'phase5.log'
$inside = '/opt/project/evidence/phase5/' + $runName
$passed = $false
$failure = $null
function Invoke-DockerLogged {
    param([string[]]$Arguments)
    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & docker @Arguments 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log -Append
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $saved }
    if ($code -ne 0) { throw "Docker command failed with exit code $code. See phase5.log." }
}
function Invoke-Quality {
    param([string]$Command,[string]$Label)
    Invoke-DockerLogged -Arguments ($compose + @('run','--rm','--entrypoint','python','cdc-tools','-m','src.quality.cli',$Command,'--evidence-dir',$inside,'--label',$Label))
    $report = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence ($Label + '.json')) | ConvertFrom-Json
    if (-not $report.passed) { throw "Phase 5 check failed: $Label" }
}
try {
    Invoke-DockerLogged -Arguments ($compose + @('config','--quiet'))
    Invoke-DockerLogged -Arguments ($compose + @('up','-d','--wait','--wait-timeout','240','mysql','postgres','kafka','connect'))
    Invoke-DockerLogged -Arguments ($compose + @('build','cdc-tools'))
    Invoke-DockerLogged -Arguments ($compose + @('up','-d','collector','applier'))
    Invoke-Quality -Command 'quality' -Label 'quality-before'
    Invoke-Quality -Command 'fixtures' -Label 'postgres-constraints-retry'
    Invoke-Quality -Command 'dimensions' -Label 'scd2-type1-cdc'
    Invoke-Quality -Command 'quality' -Label 'quality-after'
    $before = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'quality-before.json') | ConvertFrom-Json
    $after = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'quality-after.json') | ConvertFrom-Json
    if ($before.result.reconciliation.warehouse.fact_state_sha256 -ne $after.result.reconciliation.warehouse.fact_state_sha256) { throw 'Phase 5 changed historical fact state.' }
    $passed = $true
    Write-Host 'PHASE 5 QUALITY AND SCD2 CHECKS PASSED' -ForegroundColor Green
} catch {
    $failure = $_.Exception.Message
    Write-Host ('PHASE 5 CHECKS FAILED: ' + $failure) -ForegroundColor Red
} finally {
    @{ phase=5; passed=$passed; checked_at_utc=[DateTime]::UtcNow.ToString('o'); failure=$failure } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $evidence 'check.json')
    Write-Host ('Evidence: ' + $evidence)
}
if (-not $passed) { exit 1 }
