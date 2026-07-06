; =============================================================================
; installer.iss — Instalador do OWPick (Inno Setup 6)
; =============================================================================
; Gera "dist\OWPick Installer.exe" a partir do build one-folder do PyInstaller
; (dist\OWPick\). O usuário final baixa UM único executável; a pasta _internal
; fica escondida dentro do diretório de instalação.
;
; Decisões de projeto:
;   - Instalação PER-USER em {localappdata}\Programs\OWPick (sem admin/UAC).
;     Isso mantém o auto-updater (updater.py) funcionando: ele sobrescreve os
;     arquivos da instalação com robocopy, o que exige permissão de escrita.
;   - AppUserModelID nos atalhos = utils.APP_USER_MODEL_ID ("DaviGiuberti.OWPick").
;     A taskbar do Windows 11 resolve o ícone do app pelo atalho do Menu
;     Iniciar com AUMID igual ao declarado pelo processo — é isso que corrige
;     o ícone genérico de terminal na barra de tarefas.
;
; Compilação (feita automaticamente pelo build.bat):
;   ISCC.exe installer.iss
; =============================================================================

; Versão lida de version.txt (raiz do repo) — fonte única, mesma do updater.
; Este arquivo vive em packaging/, por isso os caminhos relativos usam "..".
#define VerFile FileOpen("..\version.txt")
#define AppVersion Trim(FileRead(VerFile))
#expr FileClose(VerFile)

#define AppName "OWPick"
#define AppPublisher "Davi Giuberti"
#define AppURL "https://github.com/DaviGiuberti/OWPick"
#define AppExeName "OWPick.exe"
#define AppUserModelID "DaviGiuberti.OWPick"

[Setup]
; AppId fixo: garante que futuras versões atualizem a MESMA instalação.
AppId={{09B6AE7A-2DC4-4E4B-AEAA-B5F35944FDCE}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; Per-user, sem privilégios de administrador (compatível com o auto-updater).
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes

OutputDir=..\dist
OutputBaseFilename=OWPick Installer
SetupIconFile=..\assets\icone.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

Compression=lzma2
SolidCompression=yes
WizardStyle=modern

; Impede instalar/atualizar com o OWPick aberto.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Todo o build one-folder do PyInstaller (OWPick.exe + _internal\).
Source: "..\dist\OWPick\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; AUMID idêntico ao declarado em runtime (utils.configure_windows_app_identity):
; é o vínculo que faz a taskbar do Win10/Win11 exibir o ícone correto.
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"; AppUserModelID: "{#AppUserModelID}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"; AppUserModelID: "{#AppUserModelID}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// Aviso de Termos de Serviço (tarefa 8.1): o OWPick é um observador passivo
// (só captura de tela; sem overlay, sem hook, sem automação de input), mas
// ferramentas externas são área cinzenta do ToS — o uso é por conta do usuário.
function InitializeSetup(): Boolean;
begin
  Result := MsgBox(
    'OWPick apenas captura a tela e mostra recomendacoes no terminal.' + #13#10 +
    'Ele NAO faz overlay, NAO le a memoria do jogo e NAO automatiza mouse/teclado.' + #13#10#13#10 +
    'Ainda assim, ferramentas externas de terceiros sao uma AREA CINZENTA dos ' +
    'Termos de Servico do Overwatch. O uso e por sua conta e risco.' + #13#10#13#10 +
    'Deseja continuar a instalacao?',
    mbConfirmation, MB_YESNO) = IDYES;
end;

[UninstallDelete]
; Arquivos gerados em runtime ao lado do exe (config do usuário e temporários).
Type: files; Name: "{app}\Roles.txt"
Type: files; Name: "{app}\ALL.txt"
Type: files; Name: "{app}\DPS.txt"
Type: files; Name: "{app}\SUP.txt"
Type: files; Name: "{app}\TANK.txt"
Type: files; Name: "{app}\lineup.txt"
Type: files; Name: "{app}\bans.txt"
Type: files; Name: "{app}\current_map.txt"
Type: filesandordirs; Name: "{app}\print"
