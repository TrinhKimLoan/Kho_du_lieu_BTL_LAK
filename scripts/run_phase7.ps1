$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$envFile = Join-Path $root '.runtime/lak.env'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'Existing runtime credentials are required.' }
if (-not (Test-Path -LiteralPath (Join-Path $root '.runtime/news.env'))) { throw 'Phase 6 news environment is required; keep its existing API key.' }
$base = @('compose','--project-name','lak-analytics','--env-file',$envFile,'-f',(Join-Path $root 'infra/compose.lak.yaml'))
$martCompose = $base + @('-f',(Join-Path $root 'infra/compose.mart.yaml'))
$newsCompose = $base + @('-f',(Join-Path $root 'infra/compose.news.yaml'))
$runName = 'run-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$evidence = Join-Path $root "evidence/phase7/$runName"
New-Item -ItemType Directory -Path $evidence | Out-Null
$inside = '/opt/project/evidence/phase7/' + $runName
$log = Join-Path $evidence 'phase7.log'
$passed = $false
$failure = $null
$executionDate = $null
function Invoke-DockerCheck {
    param([string[]]$Arguments,[switch]$AllowFailure)
    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $lines = @(& docker @Arguments 2>&1 | ForEach-Object { $_.ToString() })
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $saved }
    $lines | Tee-Object -FilePath $log -Append | Out-Host
    if ($code -ne 0 -and -not $AllowFailure) { throw "Docker command failed with exit code $code. See phase7.log." }
    return [pscustomobject]@{ Code=$code; Lines=$lines }
}
function Invoke-Mart {
    param([string]$Command,[string]$Label)
    $null = Invoke-DockerCheck -Arguments ($martCompose + @('run','--rm','mart-tools',$Command,'--evidence-dir',$inside,'--label',$Label))
    $report = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence ($Label+'.json')) | ConvertFrom-Json
    if (-not $report.passed) { throw "Mart check failed: $Label" }
}
try {
    $null = Invoke-DockerCheck -Arguments ($martCompose + @('config','--quiet'))
    $null = Invoke-DockerCheck -Arguments ($base + @('up','-d','--wait','--wait-timeout','240','mysql','postgres','kafka','connect','collector','applier'))
    $null = Invoke-DockerCheck -Arguments ($martCompose + @('build','mart-tools'))
    Invoke-Mart -Command 'check' -Label 'mart-checks'
    $null = Invoke-DockerCheck -Arguments ($newsCompose + @('--profile','news-scheduler','up','-d','--build','news-airflow'))
    $ready = $false
    for ($i=0; $i -lt 36; $i++) {
        $probe = Invoke-DockerCheck -AllowFailure -Arguments ($newsCompose + @('exec','-T','news-airflow','airflow','jobs','check','--job-type','SchedulerJob','--local'))
        if ($probe.Code -eq 0) { $ready=$true; break }
        Start-Sleep -Seconds 5
    }
    if (-not $ready) {
        $null = Invoke-DockerCheck -AllowFailure -Arguments ($newsCompose + @('logs','--tail','100','news-airflow'))
        throw 'Airflow scheduler did not become ready.'
    }
    $dag = 'lak_mart_refresh_phase7'
    $executionDate = [DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'")
    $null = Invoke-DockerCheck -Arguments ($newsCompose + @('exec','-T','news-airflow','airflow','dags','test','--use-executor',$dag,$executionDate))
    $state = Invoke-DockerCheck -Arguments ($newsCompose + @('exec','-T','news-airflow','airflow','dags','state',$dag,$executionDate))
    $lastLine = ($state.Lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1).Trim()
    if ($lastLine -ne 'success') { throw 'Airflow mart DagRun state is not success.' }
    Invoke-Mart -Command 'verify' -Label 'after-airflow'
    $null = Invoke-DockerCheck -Arguments ($newsCompose + @('exec','-T','news-airflow','airflow','dags','unpause',$dag))
    $null = Invoke-DockerCheck -AllowFailure -Arguments @('stats','--no-stream')
    $passed = $true
    Write-Host 'PHASE 7 MART AND OLAP CHECKS PASSED' -ForegroundColor Green
} catch {
    $failure = $_.Exception.Message
    Write-Host ('PHASE 7 CHECKS FAILED: ' + $failure) -ForegroundColor Red
} finally {
    @{phase=7; passed=$passed; execution_date=$executionDate; mart_schedule_enabled=$passed; checked_at_utc=[DateTime]::UtcNow.ToString('o'); failure=$failure} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $evidence 'check.json')
    Write-Host ('Evidence: ' + $evidence)
}
if (-not $passed) { exit 1 }
