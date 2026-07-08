; =============================================================================
; IEI Timer Faster 轻量版 — Inno Setup 安装脚本
; =============================================================================
; 构建命令: ISCC.exe installer\setup.iss
; 输出文件: dist\IEI_Timer_Faster_Lite_Setup.exe
; =============================================================================

#define MyAppName "IEI Timer Faster"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "InManage"
#define MyAppURL "http://10.111.36.3:2029"
#define MyAppExeName "IEI Timer Faster.exe"

[Setup]
AppId={{E5F6778A-3C4D-4B2E-A1F9-8C6D3B5E7A2F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=IEI_Timer_Faster_Lite_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardResizable=no
DisableProgramGroupPage=yes
VersionInfoVersion={#MyAppVersion}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: checkedonce
Name: "autostart"; Description: "开机自启"; GroupDescription: "附加任务:"

[Files]
Source: "..\dist\IEI Timer Faster\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "{app}\{#MyAppExeName}"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
function GetUninstallString: String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstPath := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1');
  sUnInstallString := '';
  if not RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

function IsUpgrade: Boolean;
begin
  Result := GetUninstallString <> '';
end;

function InitializeSetup: Boolean;
var
  sUnInstallString: String;
  iResultCode: Integer;
begin
  Result := True;

  if IsUpgrade then
  begin
    sUnInstallString := GetUninstallString;
    if MsgBox('检测到已安装的旧版本，将在安装前自动卸载。是否继续？',
      mbConfirmation, MB_YESNO) = IDYES then
    begin
      sUnInstallString := RemoveQuotes(sUnInstallString);
      if not Exec(ExpandConstant('{cmd}'), '/C ' + sUnInstallString + ' /SILENT',
        '', SW_HIDE, ewWaitUntilTerminated, iResultCode) then
      begin
        MsgBox('卸载旧版本失败，请手动卸载后重试。', mbError, MB_OK);
        Result := False;
      end;
    end
    else
      Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    Log('安装完成: ' + ExpandConstant('{app}'));
  end;
end;
