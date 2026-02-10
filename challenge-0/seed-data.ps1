# PowerShell version of seed-data.sh
$ErrorActionPreference = "Stop"

$SCRIPT_DIR = $PSScriptRoot
$CHALLENGE0_DIR = $SCRIPT_DIR
$REPO_ROOT_DIR = Split-Path $CHALLENGE0_DIR -Parent

Set-Location $CHALLENGE0_DIR

# Load environment variables from .env in repo root
$ENV_FILE = Join-Path $REPO_ROOT_DIR ".env"
if (Test-Path $ENV_FILE) {
    Get-Content $ENV_FILE | ForEach-Object {
        if ($_ -and $_ -notmatch '^\s*#' -and $_ -match '=') {
            $parts = $_ -split '=', 2
            if ($parts.Count -eq 2) {
                $name = $parts[0].Trim()
                $value = $parts[1].Trim().Trim('"')
                Set-Item -Path "env:$name" -Value $value
            }
        }
    }
    Write-Host "✅ Loaded environment variables from $ENV_FILE" -ForegroundColor Green
}
else {
    Write-Host "❌ .env file not found at $ENV_FILE. Please run challenge-0/get-keys.sh first." -ForegroundColor Red
    exit 1
}

Write-Host "🚀 Starting data seeding..." -ForegroundColor Cyan

# Extract and run the seed_data.py script from the bash script
Write-Host "🐍 Running Cosmos DB seeding script..." -Fore groundColor Cyan

# Run bash script which will generate and execute the Python scripts
bash ./seed-data.sh

Write-Host "✅ Data seeding completed!" -ForegroundColor Green
