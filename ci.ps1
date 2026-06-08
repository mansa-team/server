<#
.SYNOPSIS
    Local CI replica with auto-fix support
.DESCRIPTION
    Runs: Ruff lint, Ruff format, mypy, pytest + coverage, bandit security scan.
    Auto-fixes formatting and lint issues before checking. Exits non-zero if any required check fails.
.USAGE
    .\ci.ps1              # run all checks (auto-fix first)
    .\ci.ps1 -Lint        # lint only (auto-fix)
    .\ci.ps1 -Test        # tests only
    .\ci.ps1 -Fast        # skip bandit + mypy
    .\ci.ps1 -NoFix       # check only, no auto-fix
#>
param(
    [switch]$Lint,
    [switch]$Typecheck,
    [switch]$Test,
    [switch]$Security,
    [switch]$Fast,
    [switch]$NoFix
)

$ErrorActionPreference = "Continue"
$script:failed = @()
$script:passed = @()
$script:fixed = @()

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

function Write-Fix {
    param([string]$label)
    Write-Host "  FIXED  $label" -ForegroundColor Yellow
    $script:fixed += $label
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
if ($NoFix) { Write-Host "  (NoFix mode: check only, no auto-fix)" -ForegroundColor Yellow }

# --- Auto-fix phase ---
if (-not $NoFix -and -not $Test) {
    Write-Step "Auto-fix"

    # ruff check --fix: auto-fix safe lint issues (unused imports, etc.)
    $lintBefore = & ruff check main/ tests/ 2>&1 | Measure-Object -Line
    & ruff check --fix main/ tests/ 2>&1 | Out-Null
    $lintAfter = & ruff check main/ tests/ 2>&1 | Measure-Object -Line
    if ($lintBefore.Lines -gt $lintAfter.Lines) {
        $fixed = $lintBefore.Lines - $lintAfter.Lines
        Write-Host "  ruff check --fix: auto-fixed $fixed lint issue(s)" -ForegroundColor Yellow
    } else {
        Write-Host "  ruff check --fix: no changes needed" -ForegroundColor Gray
    }

    # ruff format: auto-format all files (not just check)
    $fmtBefore = & ruff format --check . 2>&1
    if ($LASTEXITCODE -ne 0) {
        & ruff format . 2>&1 | Out-Null
        Write-Host "  ruff format: reformatted files" -ForegroundColor Yellow
    } else {
        Write-Host "  ruff format: already formatted" -ForegroundColor Gray
    }

    Write-Host ""
}

# --- Check phase ---

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
        # Run mypy with --no-error-summary for cleaner output
        # mypy doesn't have an auto-fix mode, but we show clear errors
        Write-Step "mypy Typecheck"
        $mypyOutput = & mypy main/ 2>&1
        $mypyExit = $LASTEXITCODE
        if ($mypyOutput) { $mypyOutput | ForEach-Object { Write-Host "  $_" } }
        if ($mypyExit -eq 0) {
            Write-Pass "mypy Typecheck"
        } else {
            Write-Fail "mypy Typecheck"
            Write-Host "  Tip: mypy errors need manual fixes. Run 'mypy main/' to see details." -ForegroundColor Yellow
        }
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
if ($script:fixed.Count -gt 0) {
    Write-Host "  Auto-fixed: $($script:fixed.Count)" -ForegroundColor Yellow
    foreach ($f in $script:fixed) { Write-Host "    - $f" -ForegroundColor Yellow }
}
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
