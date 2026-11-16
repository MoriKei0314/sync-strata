# 試し用（11/16 係 T2）: 枠（Sync-Strata.exe）の子孫の WebView2 のプロセスごとに，優先度と使用率を測って並べる．
#   powershell -File measure-prio.ps1 -ShellPid 1234 -Seconds 10
# 出す物: pid, 種類（--type）, CPU の優先度, GPU の優先度（D3DKMTGet...）, CPU %（全体に対する 1 コア換算ではなく 1 コアを 100 とした値），GPU 3D %（性能カウンターの合計）
param([int]$ShellPid, [int]$Seconds = 10)
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class K {
  [DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(uint a, bool i, uint pid);
  [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
  [DllImport("gdi32.dll")] public static extern int D3DKMTGetProcessSchedulingPriorityClass(IntPtr h, out int c);
}
"@
$all = Get-CimInstance Win32_Process
$kids = @{}; foreach ($p in $all) { if (-not $kids.ContainsKey([int]$p.ParentProcessId)) { $kids[[int]$p.ParentProcessId] = @() }; $kids[[int]$p.ParentProcessId] += $p }
$found = New-Object System.Collections.ArrayList
$q = New-Object System.Collections.Queue; $q.Enqueue($ShellPid)
while ($q.Count) { $c = $q.Dequeue(); foreach ($k in $kids[[int]$c]) { [void]$found.Add($k); $q.Enqueue([int]$k.ProcessId) } }
$wv = @($found | Where-Object { $_.Name -eq 'msedgewebview2.exe' })
$cpu0 = @{}; foreach ($p in $wv) { try { $cpu0[[int]$p.ProcessId] = (Get-Process -Id $p.ProcessId).TotalProcessorTime.TotalSeconds } catch {} }
$samples = Get-Counter '\GPU Engine(*engtype_3D)\Utilization Percentage' -SampleInterval 1 -MaxSamples $Seconds
$gpu = @{}
foreach ($s in $samples) { foreach ($i in $s.CounterSamples) { if ($i.InstanceName -match 'pid_(\d+)_') { $k = [int]$Matches[1]; $gpu[$k] = [double]$gpu[$k] + $i.CookedValue } } }
$rows = foreach ($p in $wv) {
  $id = [int]$p.ProcessId
  $type = if ($p.CommandLine -match '--type=([\w-]+)') { $Matches[1] } else { 'browser' }
  $pr = $null; $g = -1
  try { $pr = (Get-Process -Id $id).PriorityClass; $cpu1 = (Get-Process -Id $id).TotalProcessorTime.TotalSeconds } catch { continue }
  $h = [K]::OpenProcess(0x1000, $false, $id)
  if ($h -ne [IntPtr]::Zero) { [void][K]::D3DKMTGetProcessSchedulingPriorityClass($h, [ref]$g); [void][K]::CloseHandle($h) }
  [pscustomobject]@{ pid = $id; type = $type; cpu_class = $pr; gpu_class = $g; cpu_pct = [math]::Round(100 * ($cpu1 - $cpu0[$id]) / $Seconds, 1); gpu3d_pct = [math]::Round([double]$gpu[$id] / $Seconds, 1) }
}
$rows | Sort-Object type, pid | Format-Table -AutoSize
"合計 CPU {0}%  GPU 3D {1}%" -f (($rows | Measure-Object cpu_pct -Sum).Sum), (($rows | Measure-Object gpu3d_pct -Sum).Sum)
