# Сборка фронтенда без ручной правки PATH (16-TZ §2).
# Использование (из папки web):  ./build.ps1
# Добавляет стандартный путь Node.js в PATH на время сборки, если node не найден.

$ErrorActionPreference = "Stop"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    $nodeDir = "C:\Program Files\nodejs"
    if (Test-Path (Join-Path $nodeDir "node.exe")) {
        $env:Path = "$nodeDir;$env:Path"
    } else {
        Write-Error "Node.js не найден. Установите Node.js и добавьте его в системный PATH (обычно C:\Program Files\nodejs)."
        exit 1
    }
}

Write-Host "node: $((Get-Command node).Source)"
npm run build
