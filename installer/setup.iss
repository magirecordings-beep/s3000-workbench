; Inno Setup script for the S3000 Workbench installer.
; Built by the GitHub workflow:  iscc /DAppVersion=1.0.0 installer\setup.iss
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "S3000 Workbench"
#define AppExe "S3000 Workbench.exe"

[Setup]
AppId={{6E0B7A52-3C1D-4F6A-9B7E-5D2C8A1F4E30}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; installs for the current user, so no administrator prompt
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=S3000-Workbench-Setup-{#AppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\{#AppName} (test tone, no sound card)"; Filename: "{app}\{#AppExe}"; Parameters: "--fake"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent

; Saved work and settings live in %LOCALAPPDATA%\S3000 Workbench and are kept on uninstall,
; so reinstalling or upgrading never loses a session.
