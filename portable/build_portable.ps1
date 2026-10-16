# Builds a self-contained Windows folder (dist\Generator) and zip that runs without installing Python.
# Run from any folder:  powershell -ExecutionPolicy Bypass -File portable\build_portable.ps1
param(
    [string]$PythonVersion = "3.12.7",
    [switch]$NoZip
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "dist"
$bundle = Join-Path $dist "Generator"
$python = Join-Path $bundle "python"
$app = Join-Path $bundle "app"

Write-Host "Building portable Generator in $bundle"
if (Test-Path $bundle) { Remove-Item -Recurse -Force $bundle }
New-Item -ItemType Directory -Force -Path $python, $app | Out-Null

# 1. Embeddable Python (official python.org build; no installer, no registry changes).
$zip = Join-Path $dist "python-$PythonVersion-embed-amd64.zip"
if (-not (Test-Path $zip)) {
    $url = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
    Write-Host "Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
}
Expand-Archive -Path $zip -DestinationPath $python -Force
# Let the embedded interpreter find installed packages.
$pth = Get-ChildItem $python -Filter "python*._pth" | Select-Object -First 1
$zipName = (Get-ChildItem $python -Filter "python*.zip" | Select-Object -First 1).Name
Set-Content -Path $pth.FullName -Encoding ASCII -Value @($zipName, ".", "Lib\site-packages", "import site")

# 2. Packages, installed with a local Python of the same minor version into the bundle.
$major, $minor = $PythonVersion.Split(".")[0..1]
$builder = $env:GENERATOR_BUILD_PYTHON
if (-not $builder) { $builder = "python" }
$builderVersion = & $builder -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"
if ($builderVersion -ne "$major.$minor") {
    throw "Build Python is $builderVersion but the bundle uses $major.$minor. Set GENERATOR_BUILD_PYTHON to a Python $major.$minor executable."
}
$site = Join-Path $python "Lib\site-packages"
& $builder -m pip install --disable-pip-version-check --no-warn-script-location --only-binary=:all: `
    --target $site -r (Join-Path $root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# 3. App files only: no tests, saved results or developer tooling.
$files = "app.py", "clinic_insights.py", "form_reader.py", "patient_forms_ui.py", "patient_records.py",
    "patient_trend.py", "risk_thresholds.py", "scoring_config.py", "scoring_config.json",
    "html_config.json", "make_test_records.py", "README.md", "USER_MANUAL.md"
foreach ($file in $files) { Copy-Item (Join-Path $root $file) $app }
New-Item -ItemType Directory -Force -Path (Join-Path $app ".streamlit") | Out-Null
Copy-Item (Join-Path $root ".streamlit\config.toml") (Join-Path $app ".streamlit")
# Only the sample forms tracked in Git: real patient PDFs added locally (Git-ignored) must never be shared.
$samples = git -C $root ls-files patient_forms
if ($LASTEXITCODE -ne 0) { throw "git ls-files failed; cannot tell sample forms from local patient forms" }
foreach ($sample in $samples) {
    $target = Join-Path $app $sample
    New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
    Copy-Item (Join-Path $root $sample) $target
}
Copy-Item (Join-Path $PSScriptRoot "Start Generator.bat"), (Join-Path $PSScriptRoot "READ ME FIRST.txt") $bundle

# 4. Smoke test: the bundled interpreter imports everything the app needs.
& (Join-Path $python "python.exe") -c "import streamlit, pandas, altair, pypdf, PIL, cv2, numpy, pyarrow; print('Bundle imports OK, Streamlit', streamlit.__version__)"
if ($LASTEXITCODE -ne 0) { throw "Bundle import check failed" }

# 5. Synthetic TEST01-TEST08 patients so Insights and trends have data; created fresh, never copied from local results.
Push-Location $app
try {
    # The embeddable Python's ._pth ignores the script folder, so add it to sys.path explicitly.
    & (Join-Path $python "python.exe") -c "import sys, runpy; sys.path.insert(0, '.'); sys.argv = ['make_test_records.py']; runpy.run_path('make_test_records.py', run_name='__main__')"
    if ($LASTEXITCODE -ne 0) { throw "Creating synthetic test records failed" }
} finally { Pop-Location }
Get-ChildItem -Recurse -Directory -Filter "__pycache__" $app | Remove-Item -Recurse -Force

if (-not $NoZip) {
    $out = Join-Path $dist "Generator-portable.zip"
    if (Test-Path $out) { Remove-Item $out }
    Write-Host "Zipping to $out (this takes a few minutes)"
    Compress-Archive -Path $bundle -DestinationPath $out -CompressionLevel Optimal
    Write-Host ("Done: {0} ({1:N0} MB)" -f $out, ((Get-Item $out).Length / 1MB))
}
