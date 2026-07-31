[CmdletBinding()]
param(
    [string]$Container = "carry_bot_container",
    [string]$ArtifactRoot = "D:\Desktop\carry_bot_2_ws\baseline_artifacts"
)

$ErrorActionPreference = "Stop"
$privateDir = Join-Path $ArtifactRoot "private\host_preflight"
$publicDir = Join-Path $ArtifactRoot "public_redacted\host_preflight"
New-Item -ItemType Directory -Force -Path $privateDir, $publicDir | Out-Null

docker ps -a --filter "name=$Container" --format "{{json .}}" |
    Set-Content -LiteralPath (Join-Path $privateDir "docker_ps.jsonl") -Encoding utf8
docker inspect $Container |
    Set-Content -LiteralPath (Join-Path $privateDir "docker_inspect.json") -Encoding utf8
$imageId = docker inspect --format "{{.Image}}" $Container
docker image inspect $imageId |
    Set-Content -LiteralPath (Join-Path $privateDir "docker_image_inspect.json") -Encoding utf8
docker version |
    Set-Content -LiteralPath (Join-Path $privateDir "docker_version.txt") -Encoding utf8
docker info --format "{{json .}}" |
    Set-Content -LiteralPath (Join-Path $privateDir "docker_info.json") -Encoding utf8

$containerId = docker inspect --format "{{.Id}}" $Container
$mounts = docker inspect --format "{{json .Mounts}}" $Container | ConvertFrom-Json
$safe = [ordered]@{
    captured_utc = [DateTime]::UtcNow.ToString("o")
    container_id_short = $containerId.Substring(0, 12)
    container_status = docker inspect --format "{{.State.Status}}" $Container
    container_created = docker inspect --format "{{.Created}}" $Container
    image_id = $imageId
    image_repo_digests = docker image inspect --format "{{json .RepoDigests}}" $imageId
    mounts = @($mounts | ForEach-Object {
        [ordered]@{ type = $_.Type; destination = $_.Destination; rw = $_.RW; propagation = $_.Propagation }
    })
    working_dir = docker inspect --format "{{.Config.WorkingDir}}" $Container
    network_mode = docker inspect --format "{{.HostConfig.NetworkMode}}" $Container
    memory_limit_bytes = docker inspect --format "{{.HostConfig.Memory}}" $Container
    nano_cpus = docker inspect --format "{{.HostConfig.NanoCpus}}" $Container
    runtime = docker inspect --format "{{.HostConfig.Runtime}}" $Container
    display_configured = [bool](docker inspect --format "{{range .Config.Env}}{{println .}}{{end}}" $Container | Select-String '^DISPLAY=')
}
$safe | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $publicDir "docker_summary.json") -Encoding utf8

Write-Output "Host preflight captured under $ArtifactRoot"
