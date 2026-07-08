; =============================================================================
; IEI Timer Faster 服务版 — Inno Setup 安装脚本
; =============================================================================
; 构建命令: ISCC.exe installer\setup.iss
; 输出文件: dist\IEI_Timer_Faster_Service_Setup.exe
;
; 与 lightweight/installer/setup.iss 的区别:
;   - 源码: dist\IEI Timer Faster Service\* (服务版 PyInstaller 产物)
;   - 集成 NSSM: 安装时注册 Windows 服务 + 自动启动，卸载时停止 + 删除
;   - 快捷方式指向 http://localhost:5000 (非 exe)
;   - 无 registry autostart (NSSM SERVICE_AUTO_START 替代)
; =============================================================================

#define MyAppName "IEI Timer Faster"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "InManage"
#define MyAppURL "http://10.111.36.3:2029"
#define MyAppServiceExe "IEI Timer Faster Service.exe"

[Setup]
AppId={{A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C}
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
OutputBaseFilename=IEI_Timer_Faster_Service_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName} (服务版)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
VersionInfoVersion={#MyAppVersion}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: checkedonce

[Files]
; 服务版 PyInstaller 产物
Source: "..\dist\IEI Timer Faster Service\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; NSSM (由 build.bat 自动下载到 ..\bin\nssm.exe)
Source: "..\bin\nssm.exe"; DestDir: "{app}"; Flags: ignoreversion
; 快捷方式图标
Source: "iei_timer.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "http://localhost:5000"; IconFilename: "{app}\iei_timer.ico"; Tasks: desktopicon
Name: "{group}\{#MyAppName}"; Filename: "http://localhost:5000"; IconFilename: "{app}\iei_timer.ico"
Name: "{group}\停止 {#MyAppName} 服务"; Filename: "{app}\nssm.exe"; Parameters: "stop ""{#MyAppName}"""
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
; 注册 Windows 服务
Filename: "{app}\nssm.exe"; Parameters: "install ""{#MyAppName}"" ""{app}\{#MyAppServiceExe}"""; \
    StatusMsg: "正在注册 Windows 服务..."; Flags: runhidden
; 设置服务为自动启动 (SERVICE_AUTO_START)
Filename: "{app}\nssm.exe"; Parameters: "set ""{#MyAppName}"" Start SERVICE_AUTO_START"; \
    StatusMsg: "正在配置服务自启动..."; Flags: runhidden
; 启动服务
Filename: "{app}\nssm.exe"; Parameters: "start ""{#MyAppName}"""; \
    StatusMsg: "正在启动服务..."; Flags: runhidden

[UninstallRun]
; 停止服务
Filename: "{app}\nssm.exe"; Parameters: "stop ""{#MyAppName}"""; Flags: runhidden; RunOnceId: "StopService"
; 删除服务
Filename: "{app}\nssm.exe"; Parameters: "remove ""{#MyAppName}"" confirm"; Flags: runhidden; RunOnceId: "RemoveService"

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
