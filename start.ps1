[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$gatewayBaseUrl = "http://localhost:8000"

$docsLinks = @(
    [PSCustomObject]@{ Name = "Gateway";  Url = "$gatewayBaseUrl/docs" },
    [PSCustomObject]@{ Name = "Auth";     Url = "http://localhost:8001/docs" },
    [PSCustomObject]@{ Name = "Huertos";  Url = "http://localhost:8002/docs" },
    [PSCustomObject]@{ Name = "Plagas";   Url = "http://localhost:8003/docs" },
    [PSCustomObject]@{ Name = "Chat";     Url = "http://localhost:8004/docs" },
    [PSCustomObject]@{ Name = "Reportes"; Url = "http://localhost:8005/docs" }
)

$gatewayRoutes = @(
    [PSCustomObject]@{ Name = "Auth";                Path = "/api/auth" },
    [PSCustomObject]@{ Name = "Usuarios";            Path = "/api/usuarios" },
    [PSCustomObject]@{ Name = "Huertos";             Path = "/api/huertos" },
    [PSCustomObject]@{ Name = "Regiones";            Path = "/api/regiones" },
    [PSCustomObject]@{ Name = "Cultivos";            Path = "/api/cultivos" },
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
    if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
        docker-compose up -d
        return
    }

    docker compose up -d
}

Write-Host ""
Write-Host "  Huerto Connect - Iniciando servicios..." -ForegroundColor Green
Write-Host ""

Start-Services
Start-Sleep -Seconds 2

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
