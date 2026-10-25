param([switch]$LiveApi,[ValidateRange(2020,2100)][int]$Year=2024,[ValidateRange(1,12)][int]$Month=12)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$envFile = Join-Path $root '.runtime/lak.env'
$newsEnv = Join-Path $root '.runtime/news.env'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'Existing phase 4/5 runtime credentials are required.' }
if (-not (Test-Path -LiteralPath $newsEnv)) { [IO.File]::WriteAllText($newsEnv,"MEDIACLOUD_API_KEY=`n",(New-Object Text.UTF8Encoding($false))) }
if ($LiveApi) {
    $newsValues = [IO.File]::ReadAllText($newsEnv)
    $keyLine = $newsValues -split "`n" | Where-Object { $_ -match '^MEDIACLOUD_API_KEY=\S+' } | Select-Object -First 1
    if (-not $keyLine) {
        $secure = Read-Host 'Nhap MediaCloud API key (khong hien tren man hinh)' -AsSecureString
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
        if ([string]::IsNullOrWhiteSpace($key) -or $key -match '\s|["''$#]') { throw 'API key contains unexpected whitespace or environment-file characters.' }
        $newsValues = ($newsValues -split "`n" | Where-Object { $_ -notmatch '^MEDIACLOUD_API_KEY=' }) -join "`n"
        [IO.File]::WriteAllText($newsEnv,($newsValues.TrimEnd()+"`nMEDIACLOUD_API_KEY=$key`n"),(New-Object Text.UTF8Encoding($false)))
        $key = $null
    }
}
$compose = @('compose','--project-name','lak-analytics','--env-file',$envFile,'-f',(Join-Path $root 'infra/compose.lak.yaml'),'-f',(Join-Path $root 'infra/compose.news.yaml'))
$runName = 'run-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$evidence = Join-Path $root "evidence/phase6/$runName"
New-Item -ItemType Directory -Path $evidence | Out-Null
$inside = '/opt/project/evidence/phase6/' + $runName
$log = Join-Path $evidence 'phase6.log'
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
    if ($code -ne 0) { throw "Docker command failed with exit code $code. See phase6.log." }
}
function Invoke-News {
    param([string]$Command,[string]$Label,[string[]]$Extra=@())
    Invoke-DockerLogged -Arguments ($compose + @('run','--rm','news-tools',$Command,'--evidence-dir',$inside,'--label',$Label) + $Extra)
    $report = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence ($Label+'.json')) | ConvertFrom-Json
    if (-not $report.passed) { throw "News check failed: $Label" }
}
try {
    Invoke-DockerLogged -Arguments ($compose + @('config','--quiet'))
    Invoke-DockerLogged -Arguments ($compose + @('up','-d','--wait','--wait-timeout','240','mysql','postgres','kafka','connect','collector','applier'))
    Invoke-DockerLogged -Arguments ($compose + @('build','news-tools'))
    Invoke-News -Command 'check' -Label 'stored-news'
    if ($LiveApi) {
        Invoke-News -Command 'fetch' -Label 'live-api' -Extra @('--year',"$Year",'--month',"$Month")
        Invoke-News -Command 'check' -Label 'after-api'
        Write-Host 'PHASE 6 NEWS PIPELINE CHECKS PASSED' -ForegroundColor Green
    } else {
        Write-Host 'PHASE 6 STORED NEWS CHECKS PASSED' -ForegroundColor Green
        Write-Host 'LIVE API NOT RUN. Use -LiveApi with a MediaCloud key before claiming live API validation.'
    }
    $passed = $true
} catch {
    $failure = $_.Exception.Message
    Write-Host ('PHASE 6 CHECKS FAILED: ' + $failure) -ForegroundColor Red
} finally {
    @{phase=6; passed=$passed; live_api_requested=[bool]$LiveApi; checked_at_utc=[DateTime]::UtcNow.ToString('o'); failure=$failure} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $evidence 'check.json')
    Write-Host ('Evidence: ' + $evidence)
}
if (-not $passed) { exit 1 }
