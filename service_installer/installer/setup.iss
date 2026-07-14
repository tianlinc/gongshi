; =============================================================================
; IEI Timer Faster 桌面版 — Inno Setup 安装脚本
; =============================================================================
; INSPUR-74: 从 Windows 后台服务（NSSM）改造为独立桌面应用。
;   用户双击快捷方式直接在 WebView2 窗口中访问，无需系统浏览器。
;
; 与改造前的区别:
;   - 移除 NSSM 服务注册/停止/删除（不再作为 Windows 后台服务运行）
;   - 快捷方式指向 exe（非 http://localhost:5000 URL）
;   - 安装后不注册服务，用户双击即用
;   - 卸载时清理应用目录，无需 NSSM 操作
;
; 构建命令: ISCC.exe installer\setup.iss
; 输出文件: dist\IEI_Timer_Faster_Setup.exe
; =============================================================================

#define MyAppName "IEI Timer Faster"
; INSPUR-82: 从项目根目录 VERSION 文件读取版本号
#define _fh FileOpen("..\..\VERSION")
#if _fh >= 0
  #define MyAppVersion FileRead(_fh)
  #expr FileClose(_fh)
#else
  #define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "InManage"
#define MyAppURL "http://10.111.36.3:2029"
#define MyAppExe "IEI Timer Faster.exe"

[Setup]
; INSPUR-93: AppId 禁止使用 {{}} 格式——ISPP 预处理器会每次编译生成随机 GUID，
; 导致不同 CI 构建产生不同 AppId，安装包互不认识。直接写固定 GUID 字符串。
AppId={A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C}
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
OutputBaseFilename=IEI_Timer_Faster_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
DisableDirPage=auto
CloseApplications=force
VersionInfoVersion={#MyAppVersion}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: checkedonce

[Files]
; PyInstaller 产物（onedir 目录）
; INSPUR-93: ignoreversion 会在升级时跳过已存在的 VERSION 文件。
; 配合 [InstallDelete] 在安装前删除旧 VERSION，确保每次安装后版本号正确。
Source: "..\dist\IEI Timer Faster\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; 快捷方式图标
Source: "iei_timer.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; 桌面快捷方式 → 指向 exe（不是 URL）
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; IconFilename: "{app}\iei_timer.ico"; Tasks: desktopicon
; 开始菜单
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; IconFilename: "{app}\iei_timer.ico"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"

; INSPUR-93: 安装前删除旧 VERSION 文件，确保升级后版本号更新。
; ignoreversion 会跳过已存在的 VERSION，通过 InstallDelete 在复制前清除旧文件，
; 这样 ignoreversion 检查时目标路径不存在同名文件，新 VERSION 一定能被复制。
[InstallDelete]
Type: files; Name: "{app}\VERSION"

[Code]
function IsSilentInstall: Boolean;
begin
  Result := Pos('/VERYSILENT', UpperCase(GetCmdTail)) > 0;
end;

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

function GetInstallDir: String;
var
  sUninstallString: String;
begin
  Result := '';
  sUninstallString := GetUninstallString;
  { UninstallString 格式: "C:\...\unins000.exe" → 提取目录 }
  if sUninstallString <> '' then
  begin
    sUninstallString := RemoveQuotes(sUninstallString);
    Result := ExtractFilePath(sUninstallString);
  end;
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

    { 静默安装：直接卸载旧版本，不弹确认对话框 }
    if IsSilentInstall then
    begin
      sUnInstallString := RemoveQuotes(sUnInstallString);
      if not Exec(ExpandConstant('{cmd}'), '/C ' + '"' + sUnInstallString + '" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART',
        '', SW_HIDE, ewWaitUntilTerminated, iResultCode) then
      begin
        Log('静默卸载旧版本失败，继续安装覆盖');
      end;
    end
    else
    begin
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
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    Log('安装完成: ' + ExpandConstant('{app}'));
  end;
end;
