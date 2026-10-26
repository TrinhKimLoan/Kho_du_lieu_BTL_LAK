$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$envFile = Join-Path $root '.runtime/lak.env'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'Keep the existing runtime credentials.' }
$compose = @('compose','--project-name','lak-analytics','--env-file',$envFile,'-f',(Join-Path $root 'infra/compose.lak.yaml'),'-f',(Join-Path $root 'infra/compose.inference.yaml'),'--profile','ml-inference')
$runName = 'run-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$evidence = Join-Path $root "evidence/phase10/$runName"
New-Item -ItemType Directory -Path $evidence | Out-Null
$inside = '/opt/project/evidence/phase10/' + $runName
$log = Join-Path $evidence 'phase10.log'
$passed = $false
$failure = $null
$workerStopped = $false
$seedReady = $false
function Invoke-DockerLogged {
    param([string[]]$Arguments)
    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & docker @Arguments 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log -Append
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $saved }
    if ($code -ne 0) { throw "Docker command failed with exit code $code. See phase10.log." }
}
try {
    Invoke-DockerLogged -Arguments ($compose + @('config','--quiet'))
    Invoke-DockerLogged -Arguments ($compose + @('up','-d','--wait','--wait-timeout','240','postgres'))
    Invoke-DockerLogged -Arguments ($compose + @('build','inference-tools'))
    Invoke-DockerLogged -Arguments ($compose + @('run','--rm','--entrypoint','python','inference-tools','-m','unittest','discover','-s','tests','-p','test_phase10*.py','-v'))
    Invoke-DockerLogged -Arguments ($compose + @('run','--rm','inference-tools','init','--evidence-dir',$inside,'--label','init'))
    Invoke-DockerLogged -Arguments ($compose + @('stop','-t','10','inference-worker'))
    $workerStopped = $true
    Invoke-DockerLogged -Arguments ($compose + @('run','--rm','inference-tools','seed','--evidence-dir',$inside,'--label','seed'))
    $seedReady = $true
    Invoke-DockerLogged -Arguments ($compose + @('up','-d','--wait','--wait-timeout','240','inference-worker'))
    $workerStopped = $false
    Invoke-DockerLogged -Arguments ($compose + @('run','--rm','inference-tools','status','--evidence-dir',$inside,'--label','status'))
    Invoke-DockerLogged -Arguments ($compose + @('run','--rm','inference-tools','finish','--seed-file',($inside+'/seed.json'),'--evidence-dir',$inside,'--label','checks'))
    $checks = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'checks.json') | ConvertFrom-Json
    if (-not $checks.passed) { throw 'CDC to ML checks did not pass.' }
    $passed = $true
} catch {
    $failure = $_.Exception.Message
} finally {
    if ($workerStopped) {
        try {
            Invoke-DockerLogged -Arguments ($compose + @('up','-d','inference-worker'))
        } catch {
            $passed = $false
            $failure = [string]$failure + ' Worker resume failed: ' + $_.Exception.Message
        }
    }
    if ($seedReady) {
        try {
            Invoke-DockerLogged -Arguments ($compose + @('run','--rm','inference-tools','cleanup','--seed-file',($inside+'/seed.json'),'--evidence-dir',$inside,'--label','cleanup'))
        } catch {
            $passed = $false
            $failure = [string]$failure + ' Demo cleanup failed: ' + $_.Exception.Message
        }
    }
    @{phase=10; passed=$passed; checked_at_utc=[DateTime]::UtcNow.ToString('o'); failure=$failure} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $evidence 'check.json')
}
if ($passed) {
    Write-Host 'PHASE 10 CDC TO ML INFERENCE CHECKS PASSED' -ForegroundColor Green
} else {
    Write-Host ('PHASE 10 CHECKS FAILED: ' + $failure) -ForegroundColor Red
}
Write-Host ('Evidence: ' + $evidence)
if (-not $passed) { exit 1 }
