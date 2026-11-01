#define MyAppName "Gestor Financiero"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "Gestor Financiero"
#define MyAppExeName "GestorFinanciero.exe"

[Setup]
AppId={{A22D7BB6-BE57-4D22-B6E7-4A6A0BFE041C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Gestor Financiero
DefaultGroupName={#MyAppName}
OutputDir=output
OutputBaseFilename=GestorFinancieroSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64

[Files]
Source: "..\dist\GestorFinanciero\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Gestor Financiero"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Gestor Financiero"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Gestor Financiero"; Flags: nowait postinstall skipifsilent
