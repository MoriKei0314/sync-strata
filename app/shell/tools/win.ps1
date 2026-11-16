# Test helper (ASCII only). Lists / closes / captures the top-level windows of one process id.
#   win.ps1 -ProcId 123 -Action list
#   win.ps1 -ProcId 123 -Action close -Title "Sync-Strata"          (posts WM_CLOSE = the user pressing the X button)
#   win.ps1 -ProcId 123 -Action shot  -Title "Sync-Strata" -Out a.png (PrintWindow: only that window, with its frame)
#   -Hwnd <handle> picks the window by its handle (as printed by list) instead of the title
param([int]$ProcId, [string]$Action = "list", [string]$Title = "", [string]$Out = "", [long]$Hwnd = 0)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Text; using System.Collections.Generic; using System.Runtime.InteropServices;
public static class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  public static List<IntPtr> Of(uint pid) {
    var r = new List<IntPtr>();
    EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p); if (p == pid && IsWindowVisible(h)) r.Add(h); return true; }, IntPtr.Zero);
    return r;
  }
  public static string Text(IntPtr h) { var s = new StringBuilder(512); GetWindowText(h, s, 512); return s.ToString(); }
}
"@
$hs = [W]::Of([uint32]$ProcId) | Where-Object { $t = [W]::Text($_); $t -ne "" -and ($Title -eq "" -or $t -eq $Title) }
if ($Action -eq "list") { foreach ($h in $hs) { "{0} {1}" -f $h, [W]::Text($h) }; exit 0 }
if (-not $hs) { Write-Host "no window"; exit 2 }
$h = @($hs)[0]
if ($Hwnd -ne 0) { $h = [IntPtr]$Hwnd }
if ($Action -eq "close") { [void][W]::PostMessage($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero); Write-Host "WM_CLOSE sent"; exit 0 }
if ($Action -eq "shot") {
  $r = New-Object W+RECT; [void][W]::GetWindowRect($h, [ref]$r)
  $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
  $g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
  [void][W]::PrintWindow($h, $dc, 2); $g.ReleaseHdc($dc); $g.Dispose()
  $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose(); Write-Host "saved $Out"; exit 0
}
