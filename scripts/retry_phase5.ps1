param([Parameter(Mandatory=$true)][ValidateRange(1,2147483647)][int]$ErrorId)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$compose = @('compose','--project-name','lak-analytics','--env-file',(Join-Path $root '.runtime/lak.env'),'-f',(Join-Path $root 'infra/compose.lak.yaml'))
$runName = 'run-retry-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$evidence = '/opt/project/evidence/phase5/' + $runName
& docker @compose run --rm --entrypoint python cdc-tools -m src.quality.cli retry --error-id $ErrorId --evidence-dir $evidence --label retry
if ($LASTEXITCODE -ne 0) { throw 'Retry request failed; no event was edited or skipped.' }
& docker @compose restart applier
if ($LASTEXITCODE -ne 0) { throw 'Retry requested, but applier restart failed.' }
Write-Host ('Retry requested. Inspect evidence/phase5/' + $runName + '/retry.json and rerun scripts/run_phase5.ps1 after the worker catches up.')
