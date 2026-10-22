# Daily update: rebuild the site on this PC and publish it to GitHub Pages.
# Run by the "Loot Drop daily update" scheduled task. Output goes to update.log.

Set-Location $PSScriptRoot
$env:Path = "C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI;" + $env:Path
$env:PYTHONIOENCODING = "utf-8"
$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$log = "$PSScriptRoot\update.log"

function Log($text) { $text | Add-Content -Path $log -Encoding utf8; $text | Write-Output }

# run a program, log everything it prints, and stop if it fails
function Run($exe) {
    $output = & $exe @args 2>&1 | ForEach-Object { "$_" }
    if ($output) { Log ($output -join "`n") }
    if ($LASTEXITCODE -ne 0) { throw "$exe $args failed (exit code $LASTEXITCODE)" }
}

try {
    Log "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm') ==="
    Run git pull --rebase --quiet
    Run $python deals.py
    Run git add docs data
    & git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        Run git commit --quiet -m "Daily update $(Get-Date -Format 'yyyy-MM-dd')"
        Run git push --quiet
        Log "Published."
    } else {
        Log "No changes to publish."
    }
} catch {
    Log "ERROR: $_"
    exit 1
}
