$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root '.runtime'
$envFile = Join-Path $runtime 'lak.env'
$composeFile = Join-Path $root 'infra/compose.lak.yaml'
$runName = 'run-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$evidence = Join-Path $root "evidence/phase3/$runName"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
New-Item -ItemType Directory -Path $evidence | Out-Null
$log = Join-Path $evidence 'phase3.log'
$compose = @('compose','--project-name','lak-analytics','--env-file',$envFile,'-f',$composeFile)
$passed = $false
$failure = $null
function Invoke-DockerLogged {
    param([string[]]$DockerArguments)
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & docker @DockerArguments 2>&1 | Tee-Object -FilePath $log -Append
        $nativeCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    if ($nativeCode -ne 0) { throw "Docker command failed with exit code $nativeCode. See phase3.log." }
}
function New-LocalPassword {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return (($bytes | ForEach-Object { $_.ToString('x2') }) -join '')
}
function Invoke-SourceTool {
    param([string]$Command,[string]$Label)
    $insideEvidence = '/opt/project/evidence/phase3/' + $runName
    Invoke-DockerLogged -DockerArguments ($compose + @('run','--rm','source-tools',$Command,'--evidence-dir',$insideEvidence,'--label',$Label))
    $resultPath = Join-Path $evidence ($Label + '.json')
    if (-not (Test-Path -LiteralPath $resultPath)) { throw "Missing evidence $Label.json" }
    $report = Get-Content -Raw -Encoding UTF8 $resultPath | ConvertFrom-Json
    if (-not $report.passed) { throw "Source check did not pass: $Label" }
}
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker CLI is unavailable. Open Docker Desktop.' }
    if (-not (Test-Path -LiteralPath $envFile)) {
        $values = 'LAK_MYSQL_ROOT_PASSWORD=' + (New-LocalPassword) + "`n" + 'LAK_MYSQL_APP_PASSWORD=' + (New-LocalPassword) + "`n"
        [IO.File]::WriteAllText($envFile,$values,(New-Object Text.UTF8Encoding($false)))
        Write-Host 'Created local LAK credentials. Existing credentials will be reused on later runs.'
    }
    Invoke-DockerLogged -DockerArguments ($compose + @('config','--quiet'))
    Invoke-DockerLogged -DockerArguments ($compose + @('up','-d','--wait','--wait-timeout','180','mysql'))
    Invoke-DockerLogged -DockerArguments ($compose + @('build','source-tools'))
    Invoke-SourceTool -Command 'install' -Label 'install'
    Invoke-SourceTool -Command 'load-history' -Label 'load-first'
    Invoke-SourceTool -Command 'load-history' -Label 'load-second'
    $first = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'load-first.json') | ConvertFrom-Json
    $second = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'load-second.json') | ConvertFrom-Json
    if ($first.result.history_state_sha256 -ne $second.result.history_state_sha256) {
        throw 'Second import changed historical field values or updated_at; idempotence check failed.'
    }
    Invoke-SourceTool -Command 'constraints' -Label 'constraints'
    Invoke-SourceTool -Command 'demo-cycle' -Label 'demo-cycle'
    Invoke-SourceTool -Command 'check' -Label 'final-check'
    $final = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'final-check.json') | ConvertFrom-Json
    if ($first.result.history_state_sha256 -ne $final.result.history_state_sha256) { throw 'Historical source changed during negative checks/demo.' }
    if ($final.result.counts.orders -ne 10000 -or $final.result.counts.customers -ne 3282 -or $final.result.counts.products -ne 15 -or $final.result.provenance_rows -ne 43297) {
        throw 'Loaded record counts do not match the provided LAK baseline.'
    }
    $passed = $true
} catch {
    $failure = $_.Exception.Message
    Write-Host "PHASE 3 SOURCE CHECKS FAILED: $failure"
} finally {
    [ordered]@{phase=3;passed=$passed;checked_at_utc=[DateTime]::UtcNow.ToString('o');project='lak-analytics';database='lak_source';host_port=3310;failure=$failure} |
        ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $evidence 'check.json')
    Write-Host "Evidence: $evidence"
}
if (-not $passed) { exit 1 }
Write-Host 'PHASE 3 SOURCE CHECKS PASSED'
