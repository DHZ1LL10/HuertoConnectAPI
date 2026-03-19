[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host ""
Write-Host "  Huerto Connect - Iniciando servicios..." -ForegroundColor Green
Write-Host ""

docker-compose up -d

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host "  Huerto Connect - Servicios activos" -ForegroundColor Green
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Swagger UI - Documentacion interactiva:" -ForegroundColor Yellow
Write-Host ""
Write-Host "    [Gateway]   http://localhost:8000/docs" -ForegroundColor White
Write-Host "    [Auth]      http://localhost:8001/docs" -ForegroundColor White
Write-Host "    [Huertos]   http://localhost:8002/docs" -ForegroundColor White
Write-Host "    [Plagas]    http://localhost:8003/docs" -ForegroundColor White
Write-Host "    [Chat]      http://localhost:8004/docs" -ForegroundColor White
Write-Host "    [Reportes]  http://localhost:8005/docs" -ForegroundColor White
Write-Host ""
Write-Host "  Health Check: http://localhost:8000/api/health" -ForegroundColor White
Write-Host "  ReDoc:        http://localhost:8000/redoc" -ForegroundColor White
Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host ""
