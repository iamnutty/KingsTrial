; NSIS Installer Script for KingsTrial
; This script creates a Windows installer for KingsTrial

!include "MUI2.nsh"
!include "x64.nsh"

; --- Basic Settings ---
Name "KingsTrial"
OutFile "..\KingsTrial-Installer.exe"
InstallDir "$PROGRAMFILES\KingsTrial"

; Default compression
SetCompressor /SOLID lzma

; --- MUI Settings ---
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

; --- Installation Section ---
Section "Install KingsTrial"
    SetOutPath "$INSTDIR"
    
    ; Copy main executable
    File "KingsTrial.exe"
    
    ; Create Start Menu shortcuts
    SetOutPath "$SMPROGRAMS\KingsTrial"
    CreateShortcut "$SMPROGRAMS\KingsTrial\KingsTrial.lnk" "$INSTDIR\KingsTrial.exe"
    CreateShortcut "$SMPROGRAMS\KingsTrial\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
    
    ; Create Desktop shortcut
    CreateShortcut "$DESKTOP\KingsTrial.lnk" "$INSTDIR\KingsTrial.exe"
    
    ; Create uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    
    ; Write registry for uninstall
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KingsTrial" \
        "DisplayName" "KingsTrial"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KingsTrial" \
        "UninstallString" "$INSTDIR\Uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KingsTrial" \
        "DisplayIcon" "$INSTDIR\KingsTrial.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KingsTrial" \
        "Publisher" "KingsTrial Developer"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KingsTrial" \
        "DisplayVersion" "1.0"
SectionEnd

; --- Uninstallation Section ---
Section "Uninstall"
    ; Remove shortcuts
    Delete "$SMPROGRAMS\KingsTrial\KingsTrial.lnk"
    Delete "$SMPROGRAMS\KingsTrial\Uninstall.lnk"
    RMDir "$SMPROGRAMS\KingsTrial"
    Delete "$DESKTOP\KingsTrial.lnk"
    
    ; Remove registry
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KingsTrial"
    
    ; Remove installed files
    Delete "$INSTDIR\KingsTrial.exe"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"
SectionEnd
