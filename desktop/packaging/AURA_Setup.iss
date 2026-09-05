; AURA QUANT-X V25 — instalador Windows x64
; Compile no Windows com Inno Setup 6+ após executar PUBLISH_WINDOWS.ps1.
; Este instalador instala o shell Desktop e o backend, mas NÃO inicia
; Bridge, Engine, Voice, Telegram, Ollama, compute ou qualquer autostart.

#define MyAppName "AURA QUANT-X"
#define MyAppVersion "12.7.0"
#define MyAppFileVersion "12.7.0.6"
#define MyAppPublisher "AURA Quant-X Local"
#define MyAppExeName "Aura.QuantX.Desktop.exe"
#define MyAppId "AURA-QUANTX-V25-2026"

[Setup]
AppId={{#MyAppId}}
AppMutex=AURA_QUANTX_V25_DESKTOP_MUTEX
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://aura.local
DefaultDirName={autopf}\AURA_QUANT_X
DefaultGroupName=AURA QUANT-X
DisableProgramGroupPage=yes
OutputDir=..\..\dist_installer
OutputBaseFilename=AURA_QUANT_X_Setup_V25_x64
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
UninstallDisplayName=AURA QUANT-X V25
UninstallDisplayIcon={app}\desktop\publish\{#MyAppExeName}
VersionInfoVersion={#MyAppFileVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=AURA QUANT-X Operator OS V25
VersionInfoProductName=AURA QUANT-X
; Assinatura deve ser configurada no Windows antes da distribuição:
; SignTool=aura-signtool

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho no Ambiente de Trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
; Publicação .NET autocontida gerada por desktop\packaging\PUBLISH_WINDOWS.ps1.
Source: "..\publish\*"; DestDir: "{app}\desktop\publish"; Flags: ignoreversion recursesubdirs createallsubdirs
; Conteúdo do pacote AURA. Mantemos dados do usuário fora de {app}.
Source: "..\..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".git\*,.install-backups\*,.dedupe-archive\*,dist_installer\*,logs_instalacao\*,desktop\publish\*,desktop\bin\*,desktop\desktop_data\*,engine\data\*,data\*.duckdb,data\*.sqlite*,data\*.session,data\runtime\*,runtime\*,node_modules\*,__pycache__\*,.pytest_cache\*,.mypy_cache\*,.ruff_cache\*,.manus-logs\*,.cache\*,cache\*,caches\*,logs\*,log\*,ARQUIVO_LEGADO\*,*.pyc,*.pyo,*.log,*.tmp,*.temp,*.cache,*.zip,*.7z,*.rar,*.tar,*.gz,*.duckdb,*.sqlite,*.sqlite3,*.sqlite-*,*.session,*.session-journal"

[Dirs]
Name: "{localappdata}\AURA_QUANT_X"
Name: "{localappdata}\AURA_QUANT_X\data"
Name: "{localappdata}\AURA_QUANT_X\desktop_data"
Name: "{localappdata}\AURA_QUANT_X\logs"
Name: "{app}\backups"
Name: "{app}\logs_instalacao"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\desktop\publish\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\AURA — abertura segura"; Filename: "{cmd}"; Parameters: "/c ""{app}\AURA_ABRIR_DESKTOP_SEGURO.bat"""; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\desktop\publish\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Somente o shell visual. Nenhum backend é iniciado por padrão.
Filename: "{cmd}"; Parameters: "/c ""{app}\AURA_ABRIR_DESKTOP_SEGURO.bat"""; WorkingDir: "{app}"; Description: "Abrir AURA Desktop (sem iniciar serviços backend)"; Flags: postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs_instalacao"
; Os dados do usuário em {localappdata} são preservados deliberadamente.

[Code]
function ReadWebView2Version(RootKey: HKEY; SubKey: String; var Version: String): Boolean;
var
  V: String;
  PackedVersion: Int64;
begin
  Result := False;
  Version := '';
  if RegQueryStringValue(RootKey, SubKey, 'pv', V) then
  begin
    if StrToVersion(V, PackedVersion) and
       (ComparePackedVersion(PackedVersion, PackVersionComponents(0, 0, 0, 0)) > 0) then
    begin
      Version := V;
      Result := True;
    end;
  end;
end;

function WebView2Installed(): Boolean;
const
  WebView2ClientId = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
var
  Version: String;
  Base: String;
begin
  Result := False;
  { Official Evergreen Runtime registration paths for 64-bit Windows. }
  Base := 'Software\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WebView2ClientId;
  if ReadWebView2Version(HKLM, Base, Version) then Result := True;
  Base := 'Software\Microsoft\EdgeUpdate\Clients\' + WebView2ClientId;
  if ReadWebView2Version(HKCU, Base, Version) then Result := True;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not IsWin64 then
  begin
    MsgBox('AURA QUANT-X requer Windows 64 bits.', mbError, MB_OK);
    Result := False;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not WebView2Installed() then
    Result := 'O Microsoft Edge WebView2 Runtime não foi detectado. Instale o WebView2 Runtime Evergreen e execute este instalador novamente.';
end;
