$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$envFile = Join-Path $root '.runtime/lak.env'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'Keep the existing phase 4/7 credentials.' }
New-Item -ItemType Directory -Force -Path (Join-Path $root 'data/models') | Out-Null
$compose = @('compose','--project-name','lak-analytics','--env-file',$envFile,'-f',(Join-Path $root 'infra/compose.lak.yaml'),'-f',(Join-Path $root 'infra/compose.ml.yaml'))
$runName = 'run-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$evidence = Join-Path $root "evidence/phase8/$runName"
New-Item -ItemType Directory -Path $evidence | Out-Null
$inside = '/opt/project/evidence/phase8/' + $runName
$log = Join-Path $evidence 'phase8.log'
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
    if ($code -ne 0) { throw "Docker command failed with exit code $code. See phase8.log." }
}
try {
    Invoke-DockerLogged -Arguments ($compose + @('config','--quiet'))
    Invoke-DockerLogged -Arguments ($compose + @('up','-d','--wait','--wait-timeout','240','postgres'))
    Invoke-DockerLogged -Arguments ($compose + @('build','ml-tools'))
    Invoke-DockerLogged -Arguments ($compose + @('run','--rm','--entrypoint','python','ml-tools','-m','unittest','discover','-s','tests','-p','test_phase8*.py','-v'))
    Invoke-DockerLogged -Arguments ($compose + @('run','--rm','ml-tools','train','--evidence-dir',$inside,'--label','train'))
    $train = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'train.json') | ConvertFrom-Json
    if (-not $train.passed) { throw 'KMeans training checks failed.' }
    $modelId = $train.result.model_id
    Invoke-DockerLogged -Arguments ($compose + @('run','--rm','ml-tools','verify','--model-id',$modelId,'--evidence-dir',$inside,'--label','verify'))
    $verify = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'verify.json') | ConvertFrom-Json
    if (-not $verify.passed) { throw 'Saved KMeans verification failed.' }
    Invoke-DockerLogged -Arguments ($compose + @('run','--rm','ml-tools','train','--evidence-dir',$inside,'--label','replay'))
    $replay = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'replay.json') | ConvertFrom-Json
    if (-not $replay.passed -or $replay.result.model_id -ne $modelId -or -not $replay.result.artifact_reused) { throw 'Model snapshot replay is not idempotent.' }
    $passed = $true
    Write-Host 'PHASE 8 RFM AND KMEANS CHECKS PASSED' -ForegroundColor Green
    Write-Host ('Model: ' + (Join-Path $root ('data/models/' + $train.result.artifact_relpath)))
} catch {
    $failure = $_.Exception.Message
    Write-Host ('PHASE 8 CHECKS FAILED: ' + $failure) -ForegroundColor Red
} finally {
    @{phase=8; passed=$passed; checked_at_utc=[DateTime]::UtcNow.ToString('o'); failure=$failure} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $evidence 'check.json')
    Write-Host ('Evidence: ' + $evidence)
}
if (-not $passed) { exit 1 }
