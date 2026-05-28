$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Get-PythonCommand {
    $bundled = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $bundled) {
        return @($bundled)
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @($py.Source, "-3")
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @($python.Source)
    }
    throw "Python 3 was not found. Install Python 3 or run this from Codex once so the bundled runtime exists."
}

function Test-PortFree([int]$port) {
    $client = New-Object Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect("127.0.0.1", $port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(180)) {
            return $true
        }
        $client.EndConnect($async)
        return $false
    } catch {
        return $true
    } finally {
        $client.Close()
    }
}

$port = 8765
while (-not (Test-PortFree $port)) {
    $port += 1
    if ($port -gt 8899) {
        throw "Could not find a free local port between 8765 and 8899."
    }
}

$python = Get-PythonCommand
$url = "http://127.0.0.1:$port/"

Write-Host "Launching Icon Forge Tools on $url"
Write-Host "Close this window to stop the server."

Start-Job -ScriptBlock {
    param($targetUrl)
    Start-Sleep -Seconds 2
    Start-Process $targetUrl
} -ArgumentList $url | Out-Null

$pythonArgs = @()
if ($python.Count -gt 1) {
    $pythonArgs = $python[1..($python.Count - 1)]
}

& $python[0] @pythonArgs "frontend.py" "--port" "$port"

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Server stopped with exit code $LASTEXITCODE."
    pause
}
