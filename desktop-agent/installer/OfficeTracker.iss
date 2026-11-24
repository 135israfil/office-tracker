; Inno Setup script for the Office Tracker agent (Phase 9).
;
;   iscc installer\OfficeTracker.iss
;
; Expects dist\OfficeTrackerAgent.exe to exist — build it first with
; `pyinstaller installer/agent.spec --noconfirm`, or run installer\build.ps1 which does
; both and checks the result.
;
; Silent install for an IT rollout (README §36's "IT installs the agent"):
;
;   OfficeTrackerSetup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
;   OfficeTrackerSetup.exe /VERYSILENT /SERVER=https://office.example.com
;
; /SERVER writes the backend URL at install time so the machine only needs its
; enrolment code afterwards, not a support call about where the server is.
;
; A build can also bake in a default server URL, so a plain double-click install (no
; /SERVER= flag at all) still gets it — for handing out one installer to a whole team
; pointed at one known server:
;
;   AGENT_DEFAULT_SERVER_URL=https://office.example.com iscc installer\OfficeTracker.iss
;
; /SERVER=, if someone does pass it, still overrides this build-time default.

; Display name only — AppExeName, DefaultDirName and the data directory below stay on
; the old technical name so an already-installed machine upgrades in place instead of
; needing a manual uninstall/reinstall; AppId (unchanged) is what Inno actually matches
; an upgrade against, independent of this string.
#define AppName "OneRoof Task Manager"
#define AppPublisher "Office Management"
#define AppExeName "OfficeTrackerAgent.exe"
#define AppVersion GetEnv("AGENT_VERSION")
#if AppVersion == ""
  #define AppVersion "0.1.0"
#endif
; Baked in at build time (AGENT_DEFAULT_SERVER_URL env var), not hardcoded here — this
; script stays reusable for building a plain, unbranded installer for any deployment.
; /SERVER= on the installer's own command line still overrides it, same as before.
#define DefaultServerUrl GetEnv("AGENT_DEFAULT_SERVER_URL")

[Setup]
AppId={{7C1F5B94-6A3D-4E28-9B7A-2F5D8E4C1A60}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\OfficeTracker
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=..\dist
OutputBaseFilename=OfficeTrackerSetup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Per-machine install: one copy of the binary, whoever logs in. The agent itself runs
; per user (decision D3), which is why autostart below is HKCU and not HKLM.
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
; Unsigned builds trip SmartScreen. Sign the output if a certificate is available:
;   SignTool=standard
;   SignedUninstaller=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\docs\employee-privacy-notice.md"; DestDir: "{app}"; DestName: "PRIVACY-NOTICE.md"; Flags: ignoreversion isreadme

[Dirs]
; The agent's state lives here for every user of the machine, so it is created by the
; installer with write access for users rather than by the first agent to run — which
; would otherwise need rights a standard user does not have.
Name: "{commonappdata}\OfficeTracker"; Permissions: users-modify

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
; No "Agent status" shortcut. The exe is a windowed build — it has to be, or autostart
; would flash a console at every login — so a shortcut running --status would print to
; a stdout nobody is attached to and appear to do nothing. Status is on the tray menu,
; and support can still redirect it:
;   "C:\Program Files\OfficeTracker\OfficeTrackerAgent.exe" --status > %TEMP%gent.txt

; Autostart is deliberately NOT in a [Registry] section.
;
; It has to be HKCU: the agent needs a desktop session to read the foreground window and
; the idle timer at all (PLAN.md D3), and the device token lives in one user's Credential
; Manager, so "the user who enrolled" is the user who should get autostart. But this is a
; per-machine install running elevated, and an Inno [Registry] HKCU entry under an
; administrative install writes to the *administrator's* hive — leaving autostart
; configured for an account that will never log in, and silently absent for the person
; who will. Inno warns about exactly this ("UsedUserAreasWarning").
;
; So the value is written from [Run] with runasoriginaluser, which lands it in the
; interactive user's hive, and removed again by --uninstall-cleanup.
;
; A Scheduled Task with RestartOnFailure was tried here instead, specifically to recover
; a crash mid-session rather than leaving the agent dead until the next login. It had to
; be reverted: a process Task Scheduler launches — even with an interactive logon trigger
; — is not granted the same foreground-activation rights a Run-key process gets from being
; launched by Explorer at logon. pystray's Windows backend calls SetForegroundWindow
; before showing the tray menu specifically because TrackPopupMenuEx needs it (see its own
; comment in _win32.py); Task Scheduler denies that call silently, so the menu still
; opens and highlights — that part is the OS, not the owning window — but no click ever
; reaches a handler. A broken tray menu is a worse regression than an occasional crash
; needing a login to clear, so this reverted rather than shipped with a workaround
; (AttachThreadInput/synthetic-input tricks exist, but read as suspicious behaviour to
; antivirus/EDR software, which is its own cost for something distributed to a fleet).

[Run]
Filename: "{sys}\reg.exe"; \
    Parameters: "add ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" \
/v OfficeTrackerAgent /t REG_SZ /d ""\""{app}\{#AppExeName}\"""" /f"; \
    Flags: runhidden waituntilterminated runasoriginaluser; \
    StatusMsg: "Configuring startup..."

; Write the server URL before the agent first starts, so an unattended rollout leaves
; machines needing only their enrolment code.
Filename: "{app}\{#AppExeName}"; Parameters: "--server ""{code:GetServerUrl}"" --status"; \
    Flags: runhidden waituntilterminated runasoriginaluser; \
    Check: HasServerUrl; StatusMsg: "Configuring server address..."
Filename: "{app}\{#AppExeName}"; Description: "Start the agent now"; \
    Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
; A copy of the agent autostarted at login may still be running when uninstall begins,
; holding queue.sqlite3/agent.log/agent.lock open — the same reason CurStepChanged below
; kills it before *install*. Without this, cleanup fails on exactly the files that make
; removal a privacy requirement rather than tidiness (see next entry).
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExeName}"; \
    Flags: runhidden waituntilterminated; \
    RunOnceId: "OfficeTrackerKillBeforeCleanup"

; Removes the local queue — a record of which applications and websites were used — plus
; the config and lock files, and clears the device token from the credential store of
; whichever account the uninstall runs as. Runs before the files are deleted.
;
; Inno Setup has no `runasoriginaluser` for uninstall; it is a [Run]-only flag. So if an
; administrator uninstalls from a different account than the one that used the agent, the
; token stays in that other user's Credential Manager. That is precisely why revocation
; is server-side rather than left to this step: disabling the computer in the web app
; invalidates the token whatever remains on the machine, and the runbook makes that the
; step *before* uninstalling rather than after.
Filename: "{app}\{#AppExeName}"; Parameters: "--uninstall-cleanup"; \
    Flags: runhidden waituntilterminated; \
    RunOnceId: "OfficeTrackerCleanup"

[UninstallDelete]
; Backstop for anything the cleanup step could not remove — a queue file held open by an
; agent that was still running, most likely. Leaving activity history on a machine that
; is no longer tracked is a privacy failure, not an untidy uninstall (§31).
Type: filesandordirs; Name: "{commonappdata}\OfficeTracker"

[Code]
var
  ServerUrl: String;

function GetServerUrl(Param: String): String;
begin
  Result := ServerUrl;
end;

function HasServerUrl: Boolean;
begin
  Result := ServerUrl <> '';
end;

function InitializeSetup(): Boolean;
var
  I: Integer;
  Arg: String;
begin
  ServerUrl := '{#DefaultServerUrl}';
  for I := 1 to ParamCount do
  begin
    Arg := ParamStr(I);
    if Pos('/SERVER=', Uppercase(Arg)) = 1 then
      ServerUrl := Copy(Arg, Length('/SERVER=') + 1, MaxInt);
  end;
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  // A running agent holds its own exe open; upgrading over it would fail with a file
  // lock rather than anything that reads as a cause.
  if CurStep = ssInstall then
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExeName}', '',
         SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
