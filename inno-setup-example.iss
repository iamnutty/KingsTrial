; Inno Setup Script for KingsTrial
; Alternative installer (optional - NSIS recommended)
; Requires Inno Setup 6.0+ from: https://jrsoftware.org/isinfo.php

[Setup]
AppName=KingsTrial
AppVersion=1.0.0
AppPublisher=KingsTrial Developer
AppPublisherURL=https://github.com/yourusername/KingsTrial
AppSupportURL=https://github.com/yourusername/KingsTrial/issues
AppUpdatesURL=https://github.com/yourusername/KingsTrial/releases
DefaultDirName={autopf}\KingsTrial
DefaultGroupName=KingsTrial
AllowNoIcons=yes
LicenseFile=
OutputDir=.
OutputBaseFilename=KingsTrial-Installer
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 0,6.1

[Files]
Source: "dist\KingsTrial.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\KingsTrial"; Filename: "{app}\KingsTrial.exe"
Name: "{group}\{cm:UninstallProgram,KingsTrial}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\KingsTrial"; Filename: "{app}\KingsTrial.exe"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\KingsTrial"; Filename: "{app}\KingsTrial.exe"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\KingsTrial.exe"; Description: "{cm:LaunchProgram,KingsTrial}"; Flags: nowait postinstall skipifsilent
