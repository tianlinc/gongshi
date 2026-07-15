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
; INSPUR-93: AppId 使用双花括号 {{GUID}}（Inno Setup 转义为字面量 { ）→
; 最终 AppId 值 = {A8F3C2B1-...}（含花括号），与 v1.1.7-v1.1.9 存量安装一致。
;
; V1.1.10 曾改为纯字符串 A8F3C2B1-...（无花括号），导致新旧 AppId 不同 →
; Inno Setup 认为是不同应用 → 两个注册表项 → 两个桌面快捷方式 + 无升级检测。
; 现已回退到双花括号以匹配存量安装。
;
; @IMPORTANT: GetUninstallString() 使用 Pascal 字面量字符串（无 ExpandConstant），
; 因此两个注册表路径中的花括号不会被当作未知常量吞并。
AppId={{A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C}}
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

; INSPUR-115: 安装前删除旧文件，确保升级后干净。
; - ignoreversion 会跳过已存在的 VERSION，通过 InstallDelete 在复制前清除旧文件
; - 旧桌面快捷方式：如果不同 AppId 格式的旧版本 uninstaller 未正确清理（如 GetUninstallString
;   "先到先得"策略跳过了另一方格式的卸载），这里兜底删除，避免两份同名快捷方式共存
[InstallDelete]
Type: files; Name: "{app}\VERSION"
Type: files; Name: "{autodesktop}\{#MyAppName}.lnk"

[Code]
procedure CleanupOrphanRegistryEntries; forward;

function IsSilentInstall: Boolean;
begin
  Result := Pos('/VERYSILENT', UpperCase(GetCmdTail)) > 0;
end;

function GetUninstallStringForPath(const sRegPath: String): String;
var
  sUnInstallString: String;
begin
  sUnInstallString := '';
  if not RegQueryStringValue(HKCU, sRegPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKLM, sRegPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

function GetUninstallString: String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstallString := '';

  { 1. 先查旧格式（v1.1.9 及之前，花括号 AppId → [GUID]_is1）→ 优先兼容存量 }
  sUnInstPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C}}_is1';
  sUnInstallString := GetUninstallStringForPath(sUnInstPath);

  { 2. 查新格式（v1.1.10，纯字符串 AppId → A8F3C2B1-..._is1） }
  if sUnInstallString = '' then
  begin
    sUnInstPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C_is1';
    sUnInstallString := GetUninstallStringForPath(sUnInstPath);
  end;

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

{ ---- 双重卸载：防止两种 AppId 格式的旧版本同时存在 ----
  GetUninstallString() 是"先到先得"策略——先查花括号格式 [GUID]_is1，
  找不到才查纯字符串格式 A8F3C2B1-..._is1。
  如果用户机器上两种 AppId 格式的注册表项同时存在（因为 v1.1.7-v1.1.9
  和 v1.1.10 的 AppId 格式来回变化），第一个匹配到的会被卸载，
  另一方（v1.1.10 纯字符串格式）的 uninstaller 从未被调用，
  导致其文件和桌面快捷方式成为孤儿残留 —— 与 v1.1.11 新装的文件并存。
  TryUninstallOtherFormat() 在 InitializeSetup 中额外查找并运行另一方格式的
  uninstaller，无论 IsUpgrade 是否为 True 都执行（覆盖机器上仅存在另一方格式的边界场景）。}
procedure TryUninstallOtherFormat;
var
  sOtherPath: String;
  sOtherUninstall: String;
  iResultCode: Integer;
begin
  { 当前 AppId = [[A8F3C2B1-...]] → 花括号格式存入注册表。
    因此"另一方"是 v1.1.10 的纯字符串格式（无花括号）。 }
  sOtherPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C_is1';
  if RegQueryStringValue(HKCU, sOtherPath, 'UninstallString', sOtherUninstall) or
     RegQueryStringValue(HKLM, sOtherPath, 'UninstallString', sOtherUninstall) then
  begin
    Log('检测到另一方格式的旧版本，正在静默卸载: ' + sOtherUninstall);
    sOtherUninstall := RemoveQuotes(sOtherUninstall);
    Exec(ExpandConstant('{cmd}'), '/C ' + '"' + sOtherUninstall + '" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART',
      '', SW_HIDE, ewWaitUntilTerminated, iResultCode);
  end;
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

  { 同时清理另一方格式的旧版本（防止两种 AppId 时代的安装并存）。
    必须在 IsUpgrade 之外执行 — 如果机器上只有 v1.1.10（纯字符串）
    而没有 v1.1.7-v1.1.9（花括号），IsUpgrade 可能返回 False
    （当前 AppId 使用花括号格式，查不到纯字符串格式的注册表项），
    但 v1.1.10 的老文件仍在目录中——需要在这里卸载。 }
  TryUninstallOtherFormat;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    Log('安装完成: ' + ExpandConstant('{app}'));
    { 清理 v1.1.10 纯字符串 AppId 遗留的孤儿注册表项 }
    CleanupOrphanRegistryEntries;
  end;
end;

{ ---- 清理孤儿注册表项（v1.1.10 纯字符串 AppId 残留） ----
  v1.1.10 的 AppId=A8F3C2B1-...（无花括号）与 v1.1.9 的 AppId=[[GUID]]（花括号）
  创建了不同的注册表项。本安装器优先卸载花括号格式的旧版本，但纯字符串格式的
  v1.1.10 遗留项也可能存在，需要一并清理，否则会导致重复快捷方式和升级检测异常。}
procedure CleanupOrphanRegistryEntries;
var
  sOtherPath: String;
begin
  { 本安装器使用花括号格式 [[GUID]]，因此纯字符串格式是"另一方" }
  sOtherPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C_is1';
  if RegKeyExists(HKCU, sOtherPath) then
  begin
    Log('检测到 v1.1.10 遗留注册表项，正在清理: ' + sOtherPath);
    RegDeleteKeyIncludingSubkeys(HKCU, sOtherPath);
  end;
  if RegKeyExists(HKLM, sOtherPath) then
  begin
    Log('检测到 v1.1.10 遗留注册表项，正在清理: ' + sOtherPath);
    RegDeleteKeyIncludingSubkeys(HKLM, sOtherPath);
  end;
end;

{ 在卸载完成后清理另一方格式的注册表项 }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    CleanupOrphanRegistryEntries;
end;
