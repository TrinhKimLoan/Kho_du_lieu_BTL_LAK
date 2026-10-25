$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.runtime/lak.env'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'Phase 3 runtime credentials are missing; do not recreate passwords for an existing volume.' }
$composeFile = Join-Path $root 'infra/compose.lak.yaml'
$runName = 'run-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$evidence = Join-Path $root "evidence/phase4/$runName"
New-Item -ItemType Directory -Path $evidence | Out-Null
$log = Join-Path $evidence 'phase4.log'
$compose = @('compose','--project-name','lak-analytics','--env-file',$envFile,'-f',$composeFile)
$passed = $false
$workersStopped = $false
$failure = $null
function Invoke-DockerLogged {
    param([string[]]$DockerArguments,[string]$InputText)
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($PSBoundParameters.ContainsKey('InputText')) {
            $InputText | & docker @DockerArguments 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log -Append
        } else {
            & docker @DockerArguments 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log -Append
        }
        $nativeCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    if ($nativeCode -ne 0) { throw "Docker command failed with exit code $nativeCode. See phase4.log." }
}
function New-LocalPassword {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return (($bytes | ForEach-Object { $_.ToString('x2') }) -join '')
}
function Invoke-CdcTool {
    param([string]$Command,[string]$Label,[string[]]$Extra = @())
    $inside = '/opt/project/evidence/phase4/' + $runName
    Invoke-DockerLogged -DockerArguments ($compose + @('run','--rm','cdc-tools',$Command,'--evidence-dir',$inside,'--label',$Label) + $Extra)
    $path = Join-Path $evidence ($Label + '.json')
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing runtime evidence: $Label" }
    $report = Get-Content -Raw -Encoding UTF8 $path | ConvertFrom-Json
    if (-not $report.passed) { throw "CDC check failed: $Label" }
}
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Open Docker Desktop before running phase 4.' }
    $values = [IO.File]::ReadAllText($envFile)
    foreach ($key in @('LAK_POSTGRES_PASSWORD','LAK_CDC_PASSWORD')) {
        if ($values -notmatch ('(?m)^' + $key + '=')) { $values = $values.TrimEnd() + "`n" + $key + '=' + (New-LocalPassword) + "`n" }
    }
    [IO.File]::WriteAllText($envFile,$values,(New-Object Text.UTF8Encoding($false)))
    $cdcLine = ($values -split "`n" | Where-Object { $_ -match '^LAK_CDC_PASSWORD=' } | Select-Object -First 1).Trim()
    $cdcSecret = $cdcLine.Substring('LAK_CDC_PASSWORD='.Length)
    if ($cdcSecret -notmatch '^[a-f0-9]{64}$') { throw 'CDC password format is unexpected; no existing credentials were replaced.' }
    Invoke-DockerLogged -DockerArguments ($compose + @('config','--quiet'))
    Invoke-DockerLogged -DockerArguments ($compose + @('up','-d','--wait','--wait-timeout','240','mysql','postgres','kafka'))
    $sql = "CREATE USER IF NOT EXISTS 'lak_cdc'@'%' IDENTIFIED BY '$cdcSecret';`nGRANT SELECT ON lak_source.* TO 'lak_cdc'@'%';`nGRANT RELOAD, SHOW DATABASES, REPLICATION SLAVE, REPLICATION CLIENT, LOCK TABLES ON *.* TO 'lak_cdc'@'%';"
    Invoke-DockerLogged -DockerArguments ($compose + @('exec','-T','mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot lak_source')) -InputText $sql
    Invoke-DockerLogged -DockerArguments ($compose + @('build','cdc-tools'))
    Invoke-DockerLogged -DockerArguments ($compose + @('up','-d','connect'))
    Invoke-CdcTool -Command 'init' -Label 'init'
    Invoke-DockerLogged -DockerArguments ($compose + @('up','-d','collector','applier'))
    Invoke-CdcTool -Command 'snapshot' -Label 'snapshot'
    Invoke-CdcTool -Command 'demo' -Label 'live-crud'
    Invoke-CdcTool -Command 'replay' -Label 'replay'
    Invoke-DockerLogged -DockerArguments ($compose + @('stop','collector','applier'))
    $workersStopped = $true
    Invoke-CdcTool -Command 'recovery-seed' -Label 'recovery-seed'
    Invoke-DockerLogged -DockerArguments ($compose + @('up','-d','collector','applier'))
    $workersStopped = $false
    $seed = '/opt/project/evidence/phase4/' + $runName + '/recovery-seed.json'
    Invoke-CdcTool -Command 'recovery-finish' -Label 'recovery' -Extra @('--seed-file',$seed)
    Invoke-CdcTool -Command 'snapshot' -Label 'final-check'
    $first = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'snapshot.json') | ConvertFrom-Json
    $last = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'final-check.json') | ConvertFrom-Json
    if ($first.result.fact_state_sha256 -ne $last.result.fact_state_sha256) { throw 'Historical fact state changed across CDC/replay/recovery demos.' }
    $passed = $true
} catch {
    $failure = $_.Exception.Message
    Write-Host "PHASE 4 CDC CHECKS FAILED: $failure"
} finally {
    if ($workersStopped) {
        try { Invoke-DockerLogged -DockerArguments ($compose + @('up','-d','collector','applier')) } catch { Write-Warning 'Could not restart workers; preserve logs for diagnosis.' }
    }
    [ordered]@{phase=4;passed=$passed;checked_at_utc=[DateTime]::UtcNow.ToString('o');project='lak-analytics';failure=$failure} |
        ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $evidence 'check.json')
    Write-Host "Evidence: $evidence"
}
if (-not $passed) { exit 1 }
Write-Host 'PHASE 4 CDC CHECKS PASSED'
