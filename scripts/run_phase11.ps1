$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$envFile = Join-Path $root '.runtime/lak.env'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'Keep existing runtime credentials.' }
$compose = @('compose','--project-name','lak-analytics','--env-file',$envFile,'-f',(Join-Path $root 'infra/compose.lak.yaml'),'-f',(Join-Path $root 'infra/compose.dashboard.yaml'),'--profile','dashboard')
$runName = 'run-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$evidence = Join-Path $root "evidence/phase11/$runName"
New-Item -ItemType Directory -Path $evidence | Out-Null
$inside = '/opt/project/evidence/phase11/' + $runName
$log = Join-Path $evidence 'phase11.log'
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
    if ($code -ne 0) { throw "Docker command failed with exit code $code. See phase11.log." }
}
try {
    Invoke-DockerLogged -Arguments ($compose + @('config','--quiet'))
    Invoke-DockerLogged -Arguments ($compose + @('up','-d','--wait','--wait-timeout','240','postgres'))
    Invoke-DockerLogged -Arguments ($compose + @('build','dashboard'))
    Invoke-DockerLogged -Arguments ($compose + @('run','--rm','--entrypoint','python','dashboard-tools','-m','unittest','discover','-s','tests','-p','test_phase11*.py','-v'))
    Invoke-DockerLogged -Arguments ($compose + @('run','--rm','dashboard-tools','--evidence-dir',$inside))
    $checks = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'dashboard-checks.json') | ConvertFrom-Json
    if (-not $checks.passed) { throw 'Dashboard query or Streamlit execution checks did not pass.' }
    Invoke-DockerLogged -Arguments ($compose + @('up','-d','--wait','--wait-timeout','240','dashboard'))
    $response = Invoke-WebRequest -Uri 'http://localhost:8501/_stcore/health' -UseBasicParsing -TimeoutSec 15
    if ($response.StatusCode -ne 200) { throw 'Dashboard HTTP health check failed.' }
    $passed = $true
    Write-Host 'PHASE 11 DASHBOARD DATA AND UI CHECKS PASSED' -ForegroundColor Green
    Write-Host 'Website: http://localhost:8501'
    Write-Host 'Browser visual review still required.'
} catch {
    $failure = $_.Exception.Message
    Write-Host ('PHASE 11 CHECKS FAILED: ' + $failure) -ForegroundColor Red
} finally {
    @{phase=11; passed=$passed; browser_visual_verified=$false; checked_at_utc=[DateTime]::UtcNow.ToString('o'); failure=$failure} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $evidence 'check.json')
    Write-Host ('Evidence: ' + $evidence)
}
if (-not $passed) { exit 1 }
