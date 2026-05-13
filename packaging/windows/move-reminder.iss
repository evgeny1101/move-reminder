#define MyAppName "Move Reminder"
#define MyAppPublisher "Move Reminder"
#define MyAppExeName "move-reminder-portable.exe"

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{D036A0DF-1A25-4A58-B2F0-2C87FAAA5D62}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
SourceDir=..\..
DefaultDirName={autopf}\Move Reminder
DefaultGroupName=Move Reminder
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=move-reminder-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "dist\move-reminder-portable.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Move Reminder"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Move Reminder"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Move Reminder"; Flags: nowait postinstall skipifsilent
