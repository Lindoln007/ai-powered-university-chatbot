# Stops the project-local PostgreSQL cluster.
$pgBin = "C:\Program Files\PostgreSQL\18\bin"
$dataDir = Join-Path $PSScriptRoot "..\.pgdata"
& "$pgBin\pg_ctl.exe" -D $dataDir stop -m fast
