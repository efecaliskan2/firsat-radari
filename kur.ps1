# Fırsat Radarı — Windows kurulumu
# Kullanım (proje klasöründe):  powershell -ExecutionPolicy Bypass -File .\kur.ps1
# Yaptıkları: bağımlılıkları kurar, simgeyi üretir, Masaüstü + Başlangıç kısayollarını oluşturur.

$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Python bul (python.org / Microsoft Store kurulumları)
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
$local = Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"
if (Test-Path $local) { $py = $local }
if (-not $py) { throw "Python bulunamadı. https://www.python.org/downloads/ adresinden kur (3.11+)." }
$pyw = Join-Path (Split-Path $py) "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py }

Write-Host "Bağımlılıklar kuruluyor..."
& $py -m pip install --user -r (Join-Path $dir "requirements.txt")

& $py (Join-Path $dir "app\make_icon.py")

$sh = New-Object -ComObject WScript.Shell
$links = @(
  @{ Path = (Join-Path ([Environment]::GetFolderPath("Desktop")) "Fırsat Radarı.lnk"); Args = "`"$dir\main.py`"" },
  @{ Path = (Join-Path ([Environment]::GetFolderPath("Startup")) "Fırsat Radarı.lnk"); Args = "`"$dir\main.py`" --tray" }
)
foreach ($l in $links) {
  $s = $sh.CreateShortcut($l.Path)
  $s.TargetPath = $pyw; $s.Arguments = $l.Args; $s.WorkingDirectory = $dir
  $s.IconLocation = Join-Path $dir "app\icon.ico"; $s.Description = "Fırsat Radarı"; $s.Save()
  Write-Host "Kısayol: $($l.Path)"
}

Write-Host "Tamam. Masaüstündeki 'Fırsat Radarı' ile aç; bilgisayar açılınca tepside kendiliğinden başlar."
