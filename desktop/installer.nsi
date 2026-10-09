; UAD 3.6 desktop -- the Windows installer.  Built by desktop/build.py:
;   makensis -DVERSION=1.0.0 -DSTAGE=<staged files> -DOUTFILE=<setup.exe> installer.nsi
;
; * Per-user install (%LOCALAPPDATA%\Programs\UAD36): no administrator rights.
; * The licence key is asked before anything is installed and checked by
;   engine/app/license.py with the bundled Python against license.json (a
;   PBKDF2 verifier -- the key itself is not in this installer).  The key is
;   handed over in a temporary file, never on a command line.
; * A silent install (/S) needs /KEY=<key>.
; * The reports live in %LOCALAPPDATA%\UAD36 and survive an update; the
;   uninstaller asks before removing them.

Unicode true
Target amd64-unicode
!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

!ifndef VERSION
  !error "VERSION is not defined"
!endif
!ifndef STAGE
  !error "STAGE is not defined"
!endif
!ifndef OUTFILE
  !error "OUTFILE is not defined"
!endif

Name "UAD 3.6"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\UAD36"
InstallDirRegKey HKCU "Software\UAD36" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
BrandingText "UAD 3.6 desktop ${VERSION}"
ShowInstDetails nevershow
ShowUninstDetails nevershow

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "UAD 3.6"
VIAddVersionKey "FileDescription" "UAD 3.6 desktop installer"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "UAD 3.6 report platform"

!define MUI_ICON "${STAGE}\icon.ico"
!define MUI_UNICON "${STAGE}\icon.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "UAD 3.6 for Windows"
!define MUI_WELCOMEPAGE_TEXT "This installs UAD 3.6 on this computer for your Windows user.$\r$\n$\r$\nThe report editor, the compliance review, the PDF and the delivery ZIP all run on this PC, and your reports are kept on this PC.$\r$\n$\r$\nYou need the licence key you were given."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Start UAD 3.6"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp

!insertmacro MUI_PAGE_WELCOME
Page custom KeyPage KeyLeave
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Var KeyField
Var KeyNote
Var Ticket
Var RuntimeReady
Var CmdKey

; ------------------------------------------------------------------ the key
Function ExtractRuntime
  ${If} $RuntimeReady != "1"
    SetOutPath "$PLUGINSDIR\rt"
    File /r /x "site-packages" "${STAGE}\python\*.*"
    SetOutPath "$PLUGINSDIR\chk"
    File "${STAGE}\app\engine\app\license.py"
    File "${STAGE}\app\engine\app\license.json"
    StrCpy $RuntimeReady "1"
  ${EndIf}
FunctionEnd

; key on the stack -> "ok" or "bad" on the stack; $Ticket set when ok
Function CheckKey
  Exch $1
  Push $2
  Push $0
  FileOpen $2 "$PLUGINSDIR\chk\key.txt" w
  FileWriteUTF16LE /BOM $2 "$1"
  FileClose $2
  nsExec::Exec '"$PLUGINSDIR\rt\python.exe" -I -S "$PLUGINSDIR\chk\license.py" check "$PLUGINSDIR\chk\key.txt" "$PLUGINSDIR\chk\license.json"'
  Pop $0
  Delete "$PLUGINSDIR\chk\key.txt"
  ${If} $0 == "0"
    FileOpen $2 "$PLUGINSDIR\chk\ticket.txt" r
    FileRead $2 $Ticket
    FileClose $2
    Delete "$PLUGINSDIR\chk\ticket.txt"
    StrCpy $1 "ok"
  ${Else}
    StrCpy $1 "bad"
  ${EndIf}
  Pop $0
  Pop $2
  Exch $1
FunctionEnd

Function .onInit
  InitPluginsDir
  ${GetParameters} $R0
  ClearErrors
  ${GetOptions} $R0 "/KEY=" $CmdKey
  ${If} ${Silent}
    ${If} $CmdKey == ""
      SetErrorLevel 2
      Abort
    ${EndIf}
    Call ExtractRuntime
    Push $CmdKey
    Call CheckKey
    Pop $0
    ${If} $0 != "ok"
      SetErrorLevel 3
      Abort
    ${EndIf}
  ${EndIf}
FunctionEnd

Function KeyPage
  !insertmacro MUI_HEADER_TEXT "Licence key" "UAD 3.6 needs your licence key to install."
  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}
  ${NSD_CreateLabel} 0 0 100% 20u "Enter the licence key you were given. It is the same key you entered on the website to download this installer."
  Pop $0
  ${NSD_CreateLabel} 0 28u 100% 10u "Licence key"
  Pop $0
  ${NSD_CreatePassword} 0 40u 100% 14u "$CmdKey"
  Pop $KeyField
  ${NSD_CreateLabel} 0 62u 100% 30u ""
  Pop $KeyNote
  ${NSD_SetFocus} $KeyField
  nsDialogs::Show
FunctionEnd

Function KeyLeave
  ${NSD_GetText} $KeyField $R1
  ${If} $R1 == ""
    MessageBox MB_ICONEXCLAMATION|MB_OK "Enter the licence key."
    Abort
  ${EndIf}
  ${NSD_SetText} $KeyNote "Checking the key..."
  Call ExtractRuntime
  Push $R1
  Call CheckKey
  Pop $0
  ${If} $0 != "ok"
    ${NSD_SetText} $KeyNote "That licence key is not valid."
    MessageBox MB_ICONSTOP|MB_OK "That licence key is not valid. Check it and try again."
    Abort
  ${EndIf}
  ${NSD_SetText} $KeyNote "Licence key accepted."
FunctionEnd

; ---------------------------------------------------------------- install
Section "UAD 3.6" SecMain
  SectionIn RO
  ${If} ${FileExists} "$LOCALAPPDATA\UAD36\run.json"
    MessageBox MB_ICONINFORMATION|MB_OKCANCEL "If UAD 3.6 is open, close its window first, then choose OK." IDOK +2
    Abort
  ${EndIf}
  ; an update replaces the program, never the reports (they are in %LOCALAPPDATA%\UAD36)
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\python"
  CreateDirectory "$INSTDIR\python"
  CopyFiles /SILENT "$PLUGINSDIR\rt\*.*" "$INSTDIR\python"
  SetOutPath "$INSTDIR\python\Lib\site-packages"
  File /r "${STAGE}\python\Lib\site-packages\*.*"
  SetOutPath "$INSTDIR\app"
  File /r "${STAGE}\app\*.*"
  SetOutPath "$INSTDIR"
  File "${STAGE}\icon.ico"

  ; the activation record the app checks at start (app/desktop.py)
  CreateDirectory "$LOCALAPPDATA\UAD36"
  FileOpen $0 "$LOCALAPPDATA\UAD36\activation.json" w
  FileWrite $0 '{"ticket": "$Ticket", "by": "installer ${VERSION}"}'
  FileClose $0

  CreateShortcut "$SMPROGRAMS\UAD 3.6.lnk" "$INSTDIR\python\pythonw.exe" '-I "$INSTDIR\app\desktop\launcher.py"' "$INSTDIR\icon.ico" 0 SW_SHOWNORMAL "" "UAD 3.6 report platform"
  CreateShortcut "$DESKTOP\UAD 3.6.lnk" "$INSTDIR\python\pythonw.exe" '-I "$INSTDIR\app\desktop\launcher.py"' "$INSTDIR\icon.ico" 0 SW_SHOWNORMAL "" "UAD 3.6 report platform"

  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\UAD36" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\UAD36" "Version" "${VERSION}"
  !define UNINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\UAD36"
  WriteRegStr HKCU "${UNINST}" "DisplayName" "UAD 3.6"
  WriteRegStr HKCU "${UNINST}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST}" "Publisher" "UAD 3.6"
  WriteRegStr HKCU "${UNINST}" "DisplayIcon" "$INSTDIR\icon.ico"
  WriteRegStr HKCU "${UNINST}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "${UNINST}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNINST}" "EstimatedSize" "$0"
SectionEnd

Function LaunchApp
  Exec '"$INSTDIR\python\pythonw.exe" -I "$INSTDIR\app\desktop\launcher.py"'
FunctionEnd

; -------------------------------------------------------------- uninstall
Section "Uninstall"
  Delete "$SMPROGRAMS\UAD 3.6.lnk"
  Delete "$DESKTOP\UAD 3.6.lnk"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\python"
  Delete "$INSTDIR\icon.ico"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\UAD36"
  DeleteRegKey HKCU "Software\UAD36"
  ${IfNot} ${Silent}
    MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 "Also delete your reports and settings stored on this PC ($LOCALAPPDATA\UAD36)?$\r$\n$\r$\nChoose No to keep them for a later installation." IDNO keep
    RMDir /r "$LOCALAPPDATA\UAD36"
  keep:
  ${EndIf}
SectionEnd
