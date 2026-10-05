param(
    [string]$StartDate = '2023-01-01',
    [string]$AsOfDate = [DateTime]::UtcNow.ToString('yyyy-MM-dd'),
    [switch]$UseLocal
)

$ErrorActionPreference = 'Stop'
$culture = [System.Globalization.CultureInfo]::InvariantCulture
$start = [DateTime]::ParseExact($StartDate, 'yyyy-MM-dd', $culture)
$cutoff = [DateTime]::ParseExact($AsOfDate, 'yyyy-MM-dd', $culture)
if ($start -ge $cutoff) { throw 'StartDate deve ser anterior a AsOfDate.' }

$projectPath = Split-Path -Parent $PSScriptRoot
$rawPath = Join-Path $projectPath 'data/raw/bitstamp_btcusd_daily.csv'
$processedPath = Join-Path $projectPath 'data/processed/btcusd_daily.csv'
$metadataPath = Join-Path $projectPath 'data/metadata.json'
$source = 'https://www.cryptodatadownload.com/cdd/Bitstamp_BTCUSD_d.csv'
New-Item -ItemType Directory -Force -Path (Split-Path $rawPath), (Split-Path $processedPath) | Out-Null

if (-not $UseLocal) {
    Invoke-WebRequest -Uri $source -UseBasicParsing -TimeoutSec 60 -OutFile $rawPath
}
if (-not (Test-Path -LiteralPath $rawPath)) { throw 'CSV original nao encontrado.' }

# A primeira linha do fornecedor e um credito, nao o cabecalho CSV.
$rawLines = @(Get-Content -LiteralPath $rawPath -Encoding UTF8)
if ($rawLines.Count -lt 3 -or $rawLines[1] -notmatch '^unix,date,symbol,open,high,low,close,Volume BTC,Volume USD') {
    throw 'Formato do CSV diferente do esperado.'
}
$records = $rawLines | Select-Object -Skip 1 | ConvertFrom-Csv
$rows = @(
    foreach ($record in $records) {
        # O unix timestamp determina o dia em UTC, sem conversao para horario local.
        $day = [DateTimeOffset]::FromUnixTimeSeconds([long]$record.unix).UtcDateTime.Date
        if ($day -lt $start -or $day -ge $cutoff) { continue }
        if ($record.symbol -ne 'BTC/USD') { throw 'Par de moeda inesperado.' }
        $close = [double]::Parse($record.close, $culture)
        $volume = [double]::Parse($record.'Volume BTC', $culture)
        if ([double]::IsNaN($close) -or [double]::IsInfinity($close) -or $close -le 0) {
            throw ('Fechamento invalido em ' + $day.ToString('yyyy-MM-dd'))
        }
        if ([double]::IsNaN($volume) -or [double]::IsInfinity($volume) -or $volume -lt 0) {
            throw ('Volume invalido em ' + $day.ToString('yyyy-MM-dd'))
        }
        [pscustomobject]@{
            date = $day.ToString('yyyy-MM-dd')
            close = $close.ToString('R', $culture)
            volume_btc = $volume.ToString('R', $culture)
        }
    }
) | Sort-Object date
$rows = @($rows)
if ($rows.Count -eq 0) { throw 'Nenhum registro no periodo solicitado.' }
if (@($rows.date | Select-Object -Unique).Count -ne $rows.Count) { throw 'Datas duplicadas.' }
$missingDates = @()
for ($i = 1; $i -lt $rows.Count; $i++) {
    $previous = [DateTime]::ParseExact($rows[$i - 1].date, 'yyyy-MM-dd', $culture)
    $current = [DateTime]::ParseExact($rows[$i].date, 'yyyy-MM-dd', $culture)
    for ($missing = $previous.AddDays(1); $missing -lt $current; $missing = $missing.AddDays(1)) {
        $missingDates += $missing.ToString('yyyy-MM-dd')
    }
}
if ($rows[0].date -ne $StartDate -or $rows[-1].date -ne $cutoff.AddDays(-1).ToString('yyyy-MM-dd')) {
    throw 'A fonte nao cobre todo o periodo solicitado.'
}

$utf8 = [System.Text.UTF8Encoding]::new($false)
$csvLines = @($rows | ConvertTo-Csv -NoTypeInformation)
[System.IO.File]::WriteAllLines($processedPath, [string[]]$csvLines, $utf8)
$metadata = [ordered]@{
    source_url = $source
    exchange = 'Bitstamp'
    symbol = 'BTC/USD'
    frequency = 'daily'
    timezone = 'UTC'
    first_date = $rows[0].date
    last_date = $rows[-1].date
    as_of_date_exclusive = $AsOfDate
    rows = $rows.Count
    rows_2026 = @($rows | Where-Object { $_.date.StartsWith('2026-') }).Count
    missing_dates = @($missingDates)
    missing_data_policy = 'Preservar os dados reais; no treinamento, excluir janelas que atravessem dias ausentes.'
    raw_sha256 = (Get-FileHash -LiteralPath $rawPath -Algorithm SHA256).Hash.ToLowerInvariant()
    processed_sha256 = (Get-FileHash -LiteralPath $processedPath -Algorithm SHA256).Hash.ToLowerInvariant()
    validation = 'Datas unicas em ordem cronologica; fechamento positivo; volume nao negativo; lacunas registradas.'
}
[System.IO.File]::WriteAllText($metadataPath, ($metadata | ConvertTo-Json) + "`n", $utf8)
$metadata | ConvertTo-Json
