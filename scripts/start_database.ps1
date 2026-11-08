# Starts the project-local PostgreSQL cluster (port 5433) used during development.
# Run from the project folder:  powershell -ExecutionPolicy Bypass -File scripts\start_database.ps1
$pgBin = "C:\Program Files\PostgreSQL\18\bin"
$dataDir = Join-Path $PSScriptRoot "..\.pgdata"
& "$pgBin\pg_ctl.exe" -D $dataDir -o "-p 5433 -c listen_addresses=localhost" -l (Join-Path $dataDir "server.log") start
& "$pgBin\pg_isready.exe" -h 127.0.0.1 -p 5433
