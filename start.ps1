[CmdletBinding()]
param(
    [switch]$Cloudflare,
    [switch]$Build,
    [switch]$CheckOnly,
    [ValidateRange(30, 3600)]
    [int]$WaitTimeoutSeconds = 600
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$gatewayBaseUrl = "http://localhost:8000"
$composeArgs = @("compose", "--project-directory", $PSScriptRoot, "-f", (Join-Path $PSScriptRoot "docker-compose.yml"))

function Get-DeploymentSetting {
    param([string]$Name, [string]$Default = "")

    $processValue = [Environment]::GetEnvironmentVariable($Name)
    if (-not [string]::IsNullOrWhiteSpace($processValue)) { return $processValue.Trim() }
    $envPath = Join-Path $PSScriptRoot ".env"
    if (Test-Path -LiteralPath $envPath) {
        foreach ($line in Get-Content -LiteralPath $envPath -Encoding UTF8) {
            if ($line -match ("^\s*" + [regex]::Escape($Name) + "\s*=\s*(.*)$")) {
                return $Matches[1].Trim().Trim([char]34).Trim([char]39)
            }
        }
    }
    return $Default
}

if ($Cloudflare) {
    $composeArgs += @("-f", (Join-Path $PSScriptRoot "docker-compose.cloudflare.yml"))
    if ([string]::IsNullOrWhiteSpace((Get-DeploymentSetting "CLOUDFLARE_TUNNEL_TOKEN"))) {
        throw "Configura CLOUDFLARE_TUNNEL_TOKEN en el archivo .env privado antes de iniciar el tunel."
    }
    $publicHostname = Get-DeploymentSetting "CLOUDFLARE_PUBLIC_HOSTNAME" "api.huertoconnect.com"
    if ($publicHostname -notmatch '^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}$') {
        throw "CLOUDFLARE_PUBLIC_HOSTNAME debe ser un dominio, sin https://, puerto ni ruta."
    }
    $gatewayBaseUrl = "https://$publicHostname"
}

& docker @composeArgs config --quiet
if ($LASTEXITCODE -ne 0) { throw "Configuracion Docker invalida. Usa Docker Compose 2.24.4 o posterior para Cloudflare." }
if ($CheckOnly) {
    Write-Host "Configuracion Docker validada; no se iniciaron contenedores."
    if ($Cloudflare) {
        Write-Host "Configura la ruta en Cloudflare: $gatewayBaseUrl -> http://gateway:8000"
    }
    return
}

$docsLinks = @(
    [PSCustomObject]@{ Name = "Gateway";  Url = "$gatewayBaseUrl/docs" },
    [PSCustomObject]@{ Name = "Auth";     Url = "http://localhost:8001/docs" },
    [PSCustomObject]@{ Name = "Huertos";  Url = "http://localhost:8002/docs" },
    [PSCustomObject]@{ Name = "Plagas";   Url = "http://localhost:8003/docs" },
    [PSCustomObject]@{ Name = "Chat";     Url = "http://localhost:8004/docs" },
    [PSCustomObject]@{ Name = "Reportes"; Url = "http://localhost:8005/docs" }
)
if ($Cloudflare) {
    $docsLinks = @([PSCustomObject]@{ Name = "Gateway publico"; Url = "$gatewayBaseUrl/docs" })
}

$gatewayRoutes = @(
    [PSCustomObject]@{ Name = "Auth";                Path = "/api/auth" },
    [PSCustomObject]@{ Name = "Usuarios";            Path = "/api/usuarios" },
    [PSCustomObject]@{ Name = "Huertos";             Path = "/api/huertos" },
    [PSCustomObject]@{ Name = "Regiones";            Path = "/api/regiones" },
    [PSCustomObject]@{ Name = "Cultivos";            Path = "/api/cultivos" },
    [PSCustomObject]@{ Name = "Comunidad";           Path = "/api/comunidad" },
    [PSCustomObject]@{ Name = "Publico";             Path = "/api/public" },
    [PSCustomObject]@{ Name = "Notificaciones";      Path = "/api/notificaciones" },
    [PSCustomObject]@{ Name = "Dataset Imagenes";    Path = "/api/datasets/imagenes" },
    [PSCustomObject]@{ Name = "Plagas";              Path = "/api/plagas" },
    [PSCustomObject]@{ Name = "Alertas";             Path = "/api/alertas" },
    [PSCustomObject]@{ Name = "Dashboard";           Path = "/api/dashboard" },
    [PSCustomObject]@{ Name = "Modelos IA";          Path = "/api/modelos" },
    [PSCustomObject]@{ Name = "Predicciones";        Path = "/api/predicciones" },
    [PSCustomObject]@{ Name = "Datasets";            Path = "/api/datasets" },
    [PSCustomObject]@{ Name = "Recomendaciones";     Path = "/api/recomendaciones" },
    [PSCustomObject]@{ Name = "Chatbot";             Path = "/api/chatbot" },
    [PSCustomObject]@{ Name = "Reportes";            Path = "/api/reportes" },
    [PSCustomObject]@{ Name = "Auditoria";           Path = "/api/auditoria" }
)

function Write-Section {
    param([string]$Title)

    Write-Host ""
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Green
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Link {
    param(
        [string]$Label,
        [string]$Url,
        [ConsoleColor]$Color = [ConsoleColor]::White
    )

    Write-Host ("  {0,-22} {1}" -f $Label, $Url) -ForegroundColor $Color
}

function Start-Services {
    $startArgs = @("up", "-d", "--wait", "--wait-timeout", "$WaitTimeoutSeconds")
    if ($Build) { $startArgs += "--build" }
    & docker @composeArgs @startArgs
    if ($LASTEXITCODE -ne 0) { throw "No se completo el arranque. Revisa los registros de los servicios." }
}

Write-Host ""
Write-Host "  Huerto Connect - Iniciando servicios..." -ForegroundColor Green
Write-Host ""

Start-Services

Write-Section "Huerto Connect - Servicios activos"
Write-Host "  Swagger UI - Documentacion interactiva:" -ForegroundColor Yellow
Write-Host ""

foreach ($doc in $docsLinks) {
    Write-Link ("[{0}]" -f $doc.Name) $doc.Url
}

Write-Host ""
Write-Host "  Direcciones base por modulo (via Gateway):" -ForegroundColor Yellow
Write-Host ""

foreach ($route in $gatewayRoutes) {
    Write-Link ("[{0}]" -f $route.Name) ("{0}{1}" -f $gatewayBaseUrl, $route.Path)
}

Write-Host ""
Write-Link "Health Check:" ("{0}/api/health" -f $gatewayBaseUrl)
Write-Link "ReDoc:" ("{0}/redoc" -f $gatewayBaseUrl)
Write-Host ""
if ($Cloudflare) {
    Write-Host "El tunel esta conectado. La ruta publicada y el DNS se configuran en tu cuenta de Cloudflare."
    Write-Link "Diagnostico local:" "http://localhost:8000/api/health"
}
