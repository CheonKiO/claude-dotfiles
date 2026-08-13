#!/usr/bin/env bash
# Claude Code Notification 훅 → OS별 네이티브 데스크톱 알림 (전부 무설치).
#   macOS       : osascript display notification
#   WSL/Windows : powershell.exe WinRT 토스트 (-EncodedCommand, UTF-16 → 한글 안전)
#   Linux 네이티브: notify-send (libnotify)
#   그 외        : 터미널 벨
# stdin=훅 페이로드 JSON: .message=문구, .cwd=작업폴더, .session_id=세션.
# 제목에 "Claude Code · <폴더명> #<세션4자리>"를 넣어 멀티세션을 구분한다.

payload="$(cat)"
# jq가 PATH에 없을 수 있어 python3로 필드를 뽑는다. 1행=메시지, 2행=cwd, 3행=session_id.
{ read -r msg; read -r cwd; read -r sid; } < <(printf '%s' "$payload" | python3 -c 'import sys,json
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
print((d.get("message") or "확인이 필요합니다").splitlines()[0])
print(d.get("cwd") or "")
print(d.get("session_id") or "")' 2>/dev/null)
[ -z "$msg" ] && msg="확인이 필요합니다"

# 제목 = "Claude Code · <폴더> (<브랜치>)". 브랜치가 세션 구분에 제일 유용
# (멀티세션이 브랜치별 작업이라). 브랜치 없으면(비git·detached) 세션ID 4자리로 폴백.
title="Claude Code"
if [ -n "$cwd" ]; then
  title="$title · $(basename "$cwd")"
  branch="$(git -C "$cwd" rev-parse --abbrev-ref HEAD 2>/dev/null)"
  if [ -n "$branch" ] && [ "$branch" != "HEAD" ]; then
    title="$title ($branch)"
  elif [ -n "$sid" ]; then
    title="$title #${sid:0:4}"
  fi
elif [ -n "$sid" ]; then
  title="$title #${sid:0:4}"
fi

uname_s="$(uname -s 2>/dev/null)"
osrelease="$(cat /proc/sys/kernel/osrelease 2>/dev/null)"

if [ "$uname_s" = "Darwin" ]; then
  # argv로 넘겨 따옴표 이스케이프 문제를 피한다. osascript는 UTF-8 그대로 처리.
  osascript -e 'on run argv' \
            -e 'display notification (item 1 of argv) with title (item 2 of argv)' \
            -e 'end run' "$msg" "$title" >/dev/null 2>&1 || true

elif printf '%s' "$osrelease" | grep -qiE 'microsoft|wsl'; then
  # env(WSLENV)는 Windows PowerShell이 시스템 코드페이지로 읽어 한글이 깨진다.
  # 문자열을 스크립트에 박아 UTF-16LE로 통째 인코딩(-EncodedCommand)하면 코드페이지·
  # 따옴표·인젝션 모두 무관하게 안전하다. PS 문자열은 홑따옴표, 내부 ' 는 '' 로 이스케이프.
  esc() { printf '%s' "$1" | sed "s/'/''/g"; }
  et="$(esc "$title")"; em="$(esc "$msg")"
  ps="\$AppId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'
try {
  [void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
  [void][Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime]
  \$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
  \$x = \$t.GetElementsByTagName('text')
  [void]\$x.Item(0).AppendChild(\$t.CreateTextNode('$et'))
  [void]\$x.Item(1).AppendChild(\$t.CreateTextNode('$em'))
  \$toast = [Windows.UI.Notifications.ToastNotification]::new(\$t)
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier(\$AppId).Show(\$toast)
} catch {
  Add-Type -AssemblyName System.Windows.Forms
  [void][System.Windows.Forms.MessageBox]::Show('$em', '$et')
}"
  b64="$(printf '%s' "$ps" | iconv -t UTF-16LE | base64 | tr -d '\n')"
  powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand "$b64" >/dev/null 2>&1 || true

elif command -v notify-send >/dev/null 2>&1; then
  notify-send "$title" "$msg" >/dev/null 2>&1 || true

else
  printf '\a' >&2 || true
fi
