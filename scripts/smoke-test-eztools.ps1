# Phase 0 gate: verify EZ Tools on Windows Server
param(
    [string]$EzToolsRoot = "C:\ForensicFlow\tools"
)

$tools = @(
    @{ Name = "EvtxECmd"; Exe = "EvtxECmd\EvtxECmd.exe" },
    @{ Name = "MFTECmd"; Exe = "MFTECmd\MFTECmd.exe" },
    @{ Name = "RECmd"; Exe = "RECmd\RECmd.exe" },
    @{ Name = "AmcacheParser"; Exe = "AmcacheParser\AmcacheParser.exe" },
    @{ Name = "PECmd"; Exe = "PECmd\PECmd.exe" },
    @{ Name = "JLECmd"; Exe = "JLECmd\JLECmd.exe" },
    @{ Name = "LECmd"; Exe = "LECmd\LECmd.exe" }
)

$pass = 0
$fail = 0

Write-Host "EZTOOLS_ROOT=$EzToolsRoot"

foreach ($tool in $tools) {
    $path = Join-Path $EzToolsRoot $tool.Exe
    if (-not (Test-Path $path)) {
        Write-Host "SKIP $($tool.Name): not found at $path"
        $fail++
        continue
    }
    try {
        & $path --help | Out-Null
        Write-Host "PASS $($tool.Name)"
        $pass++
    } catch {
        Write-Host "FAIL $($tool.Name)"
        $fail++
    }
}

Write-Host "---"
Write-Host "Pass: $pass  Fail/SKIP: $fail"
if ($fail -gt 0) {
    Write-Host "Install tools with Get-ZimmermanTools.ps1"
    exit 1
}
Write-Host "Windows Server deployment OK."
