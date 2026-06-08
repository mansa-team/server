<#
.SYNOPSIS
    Local CI replica - runs the same checks as .github/workflows/ci.yml
.DESCRIPTION
    Runs: Ruff lint, Ruff format check, mypy, pytest + coverage, bandit security scan.
    Exits non-zero if any required check fails (bandit is advisory only).
.USAGE
    .\ci.ps1              # run all checks
    .\ci.ps1 -Lint        # lint only
    .\ci.ps1 -Test        # tests only
    .\ci.ps1 -Fast        # skip bandit + mypy
#>
param(
    [switch]$Lint,
    [switch]$Typecheck,
    [switch]$Test,
    [switch]$Security,
    [switch]$Fast
)

$ErrorActionPreference = "Continue"
$script:failed = @()
$script:passed = @()

function Write-Step {
    param([string]$label)
    Write-Host ""
    Write-Host "========================================"
    Write-Host " $label"
    Write-Host "========================================"
}

function Write-Pass {
    param([string]$label)
    Write-Host "  PASS  $label" -ForegroundColor Green
    $script:passed += $label
}

function Write-Fail {
    param([string]$label)
    Write-Host "  FAIL  $label" -ForegroundColor Red
    $script:failed += $label
}

function Run-Check {
    param([string]$label, [string]$cmd, [bool]$critical = $true)
    Write-Step $label
    $output = Invoke-Expression $cmd 2>&1
    $exitCode = $LASTEXITCODE
    if ($output) { $output | ForEach-Object { Write-Host "  $_" } }
    if ($exitCode -eq 0) {
        Write-Pass $label
    } else {
        Write-Fail $label
        if (-not $critical) {
            Write-Host "  (non-blocking - continuing)" -ForegroundColor Yellow
        }
    }
    return ($exitCode -eq 0)
}

# --- Determine which checks to run ---
$runAll = -not ($Lint -or $Typecheck -or $Test -or $Security)

$startTime = Get-Date
Write-Host "CI Replica - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor White
if ($Fast) { Write-Host "  (Fast mode: skipping mypy + bandit)" -ForegroundColor Yellow }

# 1. Ruff lint
if ($runAll -or $Lint) {
    Run-Check "Ruff Lint" "ruff check main/ tests/"
}

# 2. Ruff format check
if ($runAll -or $Lint) {
    Run-Check "Ruff Format" "ruff format --check ."
}

# 3. mypy
if ($runAll -or $Typecheck) {
    if ($Fast) {
        Write-Step "mypy (skipped in fast mode)"
    } else {
        Run-Check "mypy Typecheck" "mypy main/"
    }
}

# 4. pytest + coverage
if ($runAll -or $Test) {
    $env:PYTHONPATH = "."
    Run-Check "Tests + Coverage" "pytest --cov=main --cov-report=term-missing --cov-report=xml -q"

    # 5. Coverage threshold
    if (Test-Path "coverage.xml") {
        Write-Step "Coverage Threshold (80%)"
        $cov = python -c "import xml.etree.ElementTree as ET; tree = ET.parse('coverage.xml'); root = tree.getroot(); print(int(float(root.get('line-rate', 0)) * 100))"
        $covInt = [int]$cov
        if ($covInt -ge 80) {
            Write-Host "  Coverage: $covInt% (>= 80%)" -ForegroundColor Green
            Write-Pass "Coverage Threshold"
        } else {
            Write-Host "  Coverage: $covInt% (< 80% threshold)" -ForegroundColor Red
            Write-Fail "Coverage Threshold"
        }
    } else {
        Write-Host "  coverage.xml not found - skipping threshold check" -ForegroundColor Yellow
    }
}

# 6. Bandit security
if ($runAll -or $Security) {
    if ($Fast) {
        Write-Step "Bandit Security (skipped in fast mode)"
    } else {
        Run-Check "Bandit Security Scan" "bandit -r main/ -q" $false
    }
}

# --- Summary ---
$elapsed = ((Get-Date) - $startTime).TotalSeconds
Write-Host ""
Write-Host "========================================"
Write-Host " SUMMARY"
Write-Host "========================================"
Write-Host "  Passed: $($script:passed.Count)" -ForegroundColor Green
if ($script:failed.Count -gt 0) {
    Write-Host "  Failed: $($script:failed.Count)" -ForegroundColor Red
    foreach ($f in $script:failed) { Write-Host "    - $f" -ForegroundColor Red }
} else {
    Write-Host "  Failed: 0" -ForegroundColor Green
}
Write-Host ("  Time: {0:N1}s" -f $elapsed) -ForegroundColor Gray
Write-Host ""

if ($script:failed.Count -gt 0) { exit 1 } else { exit 0 }
