# Finds the conversation page's window (11/15, used by sync_launch.py open_gui): a visible top-level window of a browser
# (Edge, Chrome, Firefox, Brave, Vivaldi, Opera) whose title is the page's title "dsh" (Edge --app window: "dsh"; a tab:
# "dsh - ..."). Prints "found <pid> <hwnd>" or "none". With -Focus, also restores it if minimized and brings it to the front.
# Reads only window titles; changes nothing else. (ASCII only: Windows PowerShell 5.1 reads a BOM-less script in the ANSI code page.)
param([switch]$Focus)
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class SyncGuiWin {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  public static List<object[]> List() {
    var o = new List<object[]>();
    EnumWindows((h, l) => {
      if (!IsWindowVisible(h)) return true;
      var sb = new StringBuilder(512);
      GetWindowText(h, sb, 512);
      uint pid;
      GetWindowThreadProcessId(h, out pid);
      o.Add(new object[] { h, pid, sb.ToString() });
      return true;
    }, IntPtr.Zero);
    return o;
  }
}
"@
$browsers = 'msedge', 'chrome', 'firefox', 'brave', 'vivaldi', 'opera'
foreach ($w in [SyncGuiWin]::List()) {
  $title = [string]$w[2]
  if ($title -notmatch '^dsh(\s|$)') { continue }
  $p = Get-Process -Id ([int]$w[1]) -ErrorAction SilentlyContinue
  if (-not $p -or ($browsers -notcontains $p.ProcessName.ToLower())) { continue }
  $h = [IntPtr]$w[0]
  if ($Focus) {
    if ([SyncGuiWin]::IsIconic($h)) { [void][SyncGuiWin]::ShowWindowAsync($h, 9) }
    [void][SyncGuiWin]::SetForegroundWindow($h)
  }
  Write-Output ("found {0} {1}" -f $w[1], $h.ToInt64())
  exit 0
}
Write-Output 'none'
exit 0
