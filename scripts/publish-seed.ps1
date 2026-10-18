# Packs the seed data the installer ships (constants, hero/item icons, the trained model, Stratz
# aggregates and caches) and uploads it as seed-data.zip to the "seed-data" release of the private
# repository; the release build (.github/workflows/release.yml) downloads it from there.
# Run again whenever the model or the Stratz data are refreshed and a new installer should carry them.
#
#   powershell -ExecutionPolicy Bypass -File scripts\publish-seed.ps1
param([string]$Repo = "")

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
if (-not $Repo) { $Repo = (gh repo view --json nameWithOwner -q .nameWithOwner) }
$parts = foreach ($name in "constants", "icons", "model", "stratz") {
    $p = Join-Path $root "data\$name"
    if (-not (Test-Path $p)) { throw "нет ${p}: сначала обнови данные (drafter.cli constants/train/stratz)" }
    $p
}
$zip = Join-Path ([System.IO.Path]::GetTempPath()) "seed-data.zip"
Compress-Archive -Path $parts -DestinationPath $zip -Force
"{0}: {1:N1} МБ" -f $zip, ((Get-Item $zip).Length / 1MB)

# gh writes progress and "release not found" to stderr; Windows PowerShell 5.1 turns any stderr
# line of a native command into a terminating error under "Stop", so check exit codes instead
$ErrorActionPreference = "Continue"
gh release view seed-data --repo $Repo 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    gh release create seed-data --repo $Repo --latest=false `
        --title "Стартовые данные для сборки" `
        --notes "seed-data.zip: константы, иконки, модель и данные Stratz для сборки установщика в GitHub Actions. Не для установки."
    if ($LASTEXITCODE -ne 0) { throw "не удалось создать релиз seed-data в $Repo" }
}
gh release upload seed-data $zip --repo $Repo --clobber
if ($LASTEXITCODE -ne 0) { throw "не удалось загрузить seed-data.zip в $Repo" }
"готово: seed-data.zip в релизе seed-data репозитория $Repo"
