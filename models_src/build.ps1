$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$compiler = Join-Path $root 'tools\studiomdl.exe'
$expected = 'A96AFA8B711BE20E706FADCBE0F62D996812C4B3CCC3C4E3B617A3A12550276A'
if ((Get-FileHash -LiteralPath $compiler -Algorithm SHA256).Hash -ne $expected) {
    throw 'StudioMDL hash mismatch; refusing to execute.'
}
Push-Location $root
try {
    node generate.cjs
    if ($LASTEXITCODE -ne 0) { throw 'Source generation failed.' }
    foreach ($name in @('bale', 'needle')) {
        & $compiler "$name.qc" *> "$name.compile.log"
        if ($LASTEXITCODE -ne 0) { throw "StudioMDL failed for $name; see $name.compile.log" }
    }
    $output = Join-Path (Split-Path $root -Parent) 'models\seno_field'
    New-Item -ItemType Directory -Force -Path $output | Out-Null
    Copy-Item -LiteralPath (Join-Path $root 'bale.mdl'), (Join-Path $root 'needle.mdl') -Destination $output -Force
    node verify.cjs
    if ($LASTEXITCODE -ne 0) { throw 'Model validation failed.' }
} finally { Pop-Location }
