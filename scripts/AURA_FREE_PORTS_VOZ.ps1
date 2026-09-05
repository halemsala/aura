$ErrorActionPreference = 'SilentlyContinue'
foreach ($p in 8080, 8765, 8099) {
  Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object {
      Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}
