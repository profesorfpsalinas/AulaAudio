; Instalador de AulaAudio para Windows (Inno Setup 6).
; - Instalación por usuario, SIN permisos de administrador (PrivilegesRequired=lowest).
; - El programa se instala en %LOCALAPPDATA%\Programs\AulaAudio.
; - Los datos del centro están en %LOCALAPPDATA%\AulaAudio y el instalador NUNCA los modifica
;   al instalar o actualizar. Al desinstalar se pregunta explícitamente si se conservan.
; Compilar:  ISCC.exe packaging\windows\AulaAudio.iss   (tras construir dist\AulaAudio con PyInstaller)

#define AppName "AulaAudio"
#define AppVersion "1.0.0"
#define AppExe "AulaAudio.exe"

[Setup]
AppId={{6E1C2F4A-9B7D-4C1E-A8F2-3D5B7A9C0E11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=AulaAudio
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=
OutputDir=..\..\dist\instalador
OutputBaseFilename=AulaAudio-{#AppVersion}-Windows-instalador
SetupIconFile=..\aulaaudio.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
LicenseFile=..\..\LICENCIAS_TERCEROS.md

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
; Solo archivos del programa. La carpeta de datos no forma parte del paquete.
Source: "..\..\dist\AulaAudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\docs\*.md"; DestDir: "{app}\documentacion"; Flags: ignoreversion
Source: "..\..\README.md"; DestDir: "{app}\documentacion"; Flags: ignoreversion

[InstallDelete]
; En una actualización se borra la versión anterior del PROGRAMA (nunca los datos).
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Manual de usuario"; Filename: "{app}\documentacion\MANUAL_USUARIO.md"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir AulaAudio ahora"; Flags: nowait postinstall skipifsilent

[Code]
var
  RemoveData: Boolean;

function DataDir(): String;
begin
  Result := ExpandConstant('{localappdata}\AulaAudio');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    RemoveData := False;
    if DirExists(DataDir()) and not UninstallSilent() then
      RemoveData := MsgBox('¿Desea ELIMINAR también los datos de AulaAudio?' + #13#10 + #13#10 +
        'Incluyen la programación, el calendario, las listas, la configuración, las copias de seguridad ' +
        'y los registros, guardados en:' + #13#10 + DataDir() + #13#10 + #13#10 +
        'Pulse «No» para conservarlos (recomendado si va a reinstalar o actualizar). ' +
        'Sus archivos de música nunca se borran.',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
    { Quitar el inicio automático si se había activado desde la aplicación }
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'AulaAudio');
  end;
  if (CurUninstallStep = usPostUninstall) and RemoveData then
  begin
    if DelTree(DataDir(), True, True, True) then
      MsgBox('Los datos de AulaAudio se han eliminado.', mbInformation, MB_OK)
    else
      MsgBox('No se han podido eliminar todos los datos. Puede borrar a mano la carpeta:' + #13#10 + DataDir(),
        mbError, MB_OK);
  end;
end;
