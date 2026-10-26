param([string]$ProjectRoot = 'G:\LAK-Analytics')
$ErrorActionPreference = 'Stop'
Set-Location $ProjectRoot
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$folder = Join-Path $ProjectRoot "evidence/phase12/measure-$stamp"
New-Item -ItemType Directory -Path $folder | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'measure.py') -Destination (Join-Path $folder 'measure.py')
$inside = "/opt/project/evidence/phase12/measure-$stamp"
$compose = @('compose','--project-name','lak-analytics','--env-file',(Join-Path $ProjectRoot '.runtime/lak.env'),'-f',(Join-Path $ProjectRoot 'infra/compose.lak.yaml'),'-f',(Join-Path $ProjectRoot 'infra/compose.inference.yaml'))
$machine = Get-CimInstance Win32_ComputerSystem
$processors = Get-CimInstance Win32_Processor
@{captured_at_utc=[DateTime]::UtcNow.ToString('o');ram_gib=[math]::Round($machine.TotalPhysicalMemory/1GB,2);cpu=@($processors | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)} | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $folder 'host.json')
docker info --format 'Docker={{.ServerVersion}} CPU={{.NCPU}} MemoryBytes={{.MemTotal}} OS={{.OSType}}' | Set-Content -Encoding UTF8 (Join-Path $folder 'docker-engine.txt')
if ($LASTEXITCODE -ne 0) { throw 'Docker Engine unavailable.' }
$statsFile = Join-Path $folder 'resource-samples.jsonl'
$stopFile = Join-Path $folder 'sampler.stop'
$sampler = Start-Job -ArgumentList $statsFile,$stopFile -ScriptBlock {
    param($StatsFile,$StopFile)
    while (-not (Test-Path -LiteralPath $StopFile)) {
        $at = [DateTime]::UtcNow.ToString('o')
        $ids = @(docker ps -q --filter 'label=com.docker.compose.project=lak-analytics')
        if ($ids.Count -gt 0) {
            $raw = @(docker stats --no-stream --format '{{json .}}' @ids)
            $containers = @($raw | ForEach-Object { $_ | ConvertFrom-Json })
            @{captured_at_utc=$at;containers=$containers} | ConvertTo-Json -Depth 6 -Compress | Add-Content -Encoding UTF8 $StatsFile
        }
        Start-Sleep -Seconds 2
    }
}
$passed = $false
try {
    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & docker @compose run --rm -T -e PYTHONPATH=/opt/project --entrypoint python inference-tools "$inside/measure.py" --evidence-dir $inside --samples 20 2>&1 |
            ForEach-Object { $_.ToString() } | Tee-Object -FilePath (Join-Path $folder 'measurement.log') | Out-Host
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $saved }
    if ($code -ne 0) { throw 'Measurement command failed; send measurement.log and measurement.json.' }
    $result = Get-Content -Raw -Encoding UTF8 (Join-Path $folder 'measurement.json') | ConvertFrom-Json
    if (-not $result.passed) { throw 'Measurement result did not pass.' }
    $passed = $true
} finally {
    New-Item -ItemType File -Path $stopFile -Force | Out-Null
    $sampler | Wait-Job -Timeout 15 | Out-Null
    if ($sampler.State -eq 'Running') { $sampler | Stop-Job }
    Receive-Job -Job $sampler -ErrorAction Continue | Out-Host
    $sampler | Remove-Job
    docker system df | Set-Content -Encoding UTF8 (Join-Path $folder 'docker-system-df-GLOBAL.txt')
    Write-Host ('Evidence: ' + $folder)
}
if (-not (Test-Path -LiteralPath $statsFile)) { throw 'Resource sampler produced no evidence; measurement stage is incomplete.' }
if ($passed) { Write-Host 'PHASE 12 MEASUREMENTS COMPLETED' -ForegroundColor Green }
