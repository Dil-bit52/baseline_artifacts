[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RunId,
    [string]$Container = "carry_bot_container",
    [string]$OutputRoot = "D:\Desktop\carry_bot_2_ws\baseline_artifacts\docker_stats",
    [Parameter(Mandatory = $true)][string]$Command
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
$output = Join-Path $OutputRoot "$RunId.csv"
$writer = [System.IO.StreamWriter]::new($output, $false, [System.Text.UTF8Encoding]::new($false))
$writer.WriteLine("timestamp_utc,run_id,container_id,cpu_percent,memory_usage,memory_limit,memory_percent,net_io,block_io,pids")

$job = Start-Job -ArgumentList $Container, $RunId -ScriptBlock {
    param($ContainerName, $Id)
    while ($true) {
        $stamp = [DateTime]::UtcNow.ToString("o")
        $json = docker stats $ContainerName --no-stream --format "{{json .}}" 2>$null
        if ($LASTEXITCODE -eq 0 -and $json) {
            [PSCustomObject]@{ stamp = $stamp; json = $json }
        }
        Start-Sleep -Seconds 1
    }
}

try {
    $process = Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile", "-Command", $Command
    ) -NoNewWindow -Wait -PassThru
    $runExitCode = $process.ExitCode
}
finally {
    Stop-Job $job -ErrorAction SilentlyContinue
    Receive-Job $job -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $row = $_.json | ConvertFrom-Json
            $memoryParts = ([string]$row.MemUsage) -split '\s+/\s+', 2
            $memoryUsage = $memoryParts[0]
            $memoryLimit = if ($memoryParts.Count -gt 1) { $memoryParts[1] } else { "" }
            $values = @(
                $_.stamp, $RunId, $row.ID, $row.CPUPerc, $memoryUsage,
                $memoryLimit, $row.MemPerc, $row.NetIO, $row.BlockIO, $row.PIDs
            ) | ForEach-Object { '"' + ([string]$_).Replace('"', '""') + '"' }
            $writer.WriteLine(($values -join ','))
            $writer.Flush()
        }
        catch {}
    }
    $writer.Dispose()
    Remove-Job $job -Force -ErrorAction SilentlyContinue
}

exit $runExitCode
