param(
    [string]$Image = 'postgres:16.15-trixie'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$suffix = [guid]::NewGuid().ToString('N').Substring(0, 8)
$container = "lak-phase2-check-$suffix"
$runName = 'run-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + $suffix
$evidence = Join-Path $root "evidence/phase2/$runName"
$schema = Join-Path $root 'sql/phase2/001_warehouse_schema.sql'
$checks = Join-Path $root 'sql/phase2/002_schema_checks.sql'
$created = $false
$passed = $false
$imageId = $null
$failure = $null
New-Item -ItemType Directory -Path $evidence | Out-Null
$log = Join-Path $evidence 'postgres-check.log'
function Invoke-DockerLogged {
    param([string[]]$DockerArguments)
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & docker @DockerArguments 2>&1 | Tee-Object -FilePath $log -Append
        $nativeCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedPreference
    }
    if ($nativeCode -ne 0) { throw "Docker command failed with exit code $nativeCode. See postgres-check.log." }
}
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker CLI not found. Open Docker Desktop and use a shell with Docker installed.'
    }
    Invoke-DockerLogged -DockerArguments @('info','--format','{{.ServerVersion}}')

    $temporaryPassword = [guid]::NewGuid().ToString('N')
    Invoke-DockerLogged -DockerArguments @('run','--detach','--rm','--name',$container,'--network','none','--tmpfs','/var/lib/postgresql/data','-e',"POSTGRES_PASSWORD=$temporaryPassword",'-e','POSTGRES_DB=lak_phase2_check',$Image)
    $created = $true
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        & docker exec $container pg_isready -h 127.0.0.1 -U postgres -d lak_phase2_check 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'Temporary PostgreSQL did not become ready in 60 seconds.' }
    $imageId = (& docker inspect --format '{{.Image}}' $container | Out-String).Trim()
    & docker cp $schema "${container}:/tmp/lak-schema.sql"
    if ($LASTEXITCODE -ne 0) { throw 'Could not copy schema SQL.' }
    & docker cp $checks "${container}:/tmp/lak-checks.sql"
    if ($LASTEXITCODE -ne 0) { throw 'Could not copy check SQL.' }
    Invoke-DockerLogged -DockerArguments @('exec',$container,'psql','-X','-U','postgres','-d','lak_phase2_check','-v','ON_ERROR_STOP=1','-f','/tmp/lak-schema.sql')
    Invoke-DockerLogged -DockerArguments @('exec',$container,'psql','-X','-U','postgres','-d','lak_phase2_check','-v','ON_ERROR_STOP=1','-f','/tmp/lak-checks.sql')
    $passed = $true
} catch {
    $failure = $_.Exception.Message
    Write-Host "PHASE 2 POSTGRES CHECKS FAILED: $failure"
} finally {
    if ($created) {
        $savedPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & docker rm --force $container 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Warning "Could not remove temporary container $container" }
        $ErrorActionPreference = $savedPreference
    }
    $result = [ordered]@{
        phase = 2
        passed = $passed
        checked_at_utc = [DateTime]::UtcNow.ToString('o')
        image = $Image
        image_id = $imageId
        schema_sha256 = (Get-FileHash -Algorithm SHA256 $schema).Hash.ToLowerInvariant()
        checks_sha256 = (Get-FileHash -Algorithm SHA256 $checks).Hash.ToLowerInvariant()
        temporary_container = $container
        binds_host_port = $false
        uses_persistent_volume = $false
        failure = $failure
    }
    $result | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $evidence 'check.json')
    Write-Host "Evidence: $evidence"
}
if (-not $passed) { exit 1 }
Write-Host 'PHASE 2 POSTGRES CHECKS PASSED'
