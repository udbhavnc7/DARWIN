$ErrorActionPreference = 'Stop'
$version = 'v2.13.0'
$asset = 'toxiproxy-server-windows-amd64.exe'
$destination = Join-Path $PSScriptRoot '../.runtime/tools'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
$binary = Join-Path $destination 'toxiproxy-server.exe'
# Windows PowerShell 5.1 needs TLS 1.2 for GitHub and basic parsing on machines where IE was never set up.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$checksums = (Invoke-WebRequest -UseBasicParsing "https://github.com/Shopify/toxiproxy/releases/download/$version/checksums.txt").Content
if ($checksums -is [byte[]]) { $checksums = [System.Text.Encoding]::UTF8.GetString($checksums) }
$expected = ($checksums -split "`n" | Where-Object { $_.Trim().EndsWith($asset) }) -split '\s+'
if ($expected.Count -lt 2) { throw 'Release checksum missing' }
Invoke-WebRequest -UseBasicParsing "https://github.com/Shopify/toxiproxy/releases/download/$version/$asset" -OutFile $binary
if ((Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash -ne $expected[0]) { throw 'Toxiproxy checksum mismatch' }
Write-Output "Verified Toxiproxy $version at $binary"
