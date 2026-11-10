param(
    [Parameter(Mandatory = $true)][string]$Map,
    [Parameter(Mandatory = $true)][string]$Out,
    [string]$HlTools = "D:\SteamLibrary\steamapps\common\Half-Life\tools",
    [switch]$Fast
)

$ErrorActionPreference = 'Stop'
$mapPath = (Resolve-Path $Map).Path
if (Test-Path $Out) { throw "Output folder already exists: $Out" }
New-Item -ItemType Directory -Path $Out | Out-Null
Copy-Item $mapPath (Join-Path $Out 'control.map')

$stages = @(
    @{ Exe = 'hlcsg_x64.exe'; Args = @('-nowadtextures', 'control.map') },
    @{ Exe = 'hlbsp_x64.exe'; Args = @('control.map') },
    @{ Exe = 'hlvis_x64.exe'; Args = if ($Fast) { @('-fast', 'control.map') } else { @('control.map') } },
    @{ Exe = 'hlrad_x64.exe'; Args = @('control.map') }
)

Push-Location $Out
try {
    foreach ($stage in $stages) {
        $exe = Join-Path $HlTools $stage.Exe
        if (-not (Test-Path $exe)) { throw "Not found: $exe" }
        Write-Host "== $($stage.Exe) =="
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        & $exe @($stage.Args) 2>&1 | Out-File -Encoding utf8 ($stage.Exe + '.log')
        $code = $LASTEXITCODE
        $sw.Stop()
        "{0} exit={1} seconds={2}" -f $stage.Exe, $code, [math]::Round($sw.Elapsed.TotalSeconds, 1)
        if ($code -ne 0) { throw "$($stage.Exe) failed with code $code" }
    }
    $bsp = Join-Path $Out 'control.bsp'
    if (-not (Test-Path $bsp)) { throw 'control.bsp was not produced' }
    Write-Host ("BSP: {0} KB" -f [math]::Round((Get-Item $bsp).Length / 1KB, 1))
    Write-Host ("SHA256: " + (Get-FileHash $bsp -Algorithm SHA256).Hash)
}
finally {
    Pop-Location
}
