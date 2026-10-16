# Dev check for the overlay window: sends the global hotkeys (Ctrl+Shift+M / Ctrl+Shift+N) and prints
# visibility, topmost and click-through flags of the app windows. Usage: overlay-check.ps1 [-Keys toggle|interact]
param([string]$Keys = "")
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowThreadProcessId(IntPtr h, out int pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, int flags, IntPtr extra);
  public struct RECT { public int L, T, R, B; }
}
"@
function Press([byte[]]$vks) {
  foreach ($k in $vks) { [W]::keybd_event($k, 0, 0, [IntPtr]::Zero) }
  Start-Sleep -Milliseconds 60
  [array]::Reverse($vks)
  foreach ($k in $vks) { [W]::keybd_event($k, 0, 2, [IntPtr]::Zero) }
}
if ($Keys -eq "toggle") { Press @(0x11, 0x10, 0x4D); Start-Sleep -Milliseconds 700 }   # Ctrl+Shift+M
if ($Keys -eq "interact") { Press @(0x11, 0x10, 0x4E); Start-Sleep -Milliseconds 700 } # Ctrl+Shift+N
$procIds = (Get-Process app -ErrorAction SilentlyContinue).Id
$global:found = New-Object System.Collections.ArrayList
[W]::EnumWindows({ param($h, $l)
  $p = 0; [void][W]::GetWindowThreadProcessId($h, [ref]$p)
  if ($procIds -contains $p) {
    $sb = New-Object System.Text.StringBuilder 256; [void][W]::GetWindowText($h, $sb, 256)
    $t = $sb.ToString()
    if ($t -like "Dota Drafter*") {
      $ex = [W]::GetWindowLong($h, -20); $r = New-Object W+RECT; [void][W]::GetWindowRect($h, [ref]$r)
      [void]$global:found.Add(("{0} | visible={1} topmost={2} layered={3} click-through={4} rect={5},{6} {7}x{8}" -f $t, [W]::IsWindowVisible($h),
        [bool]($ex -band 0x8), [bool]($ex -band 0x80000), [bool]($ex -band 0x20), $r.L, $r.T, ($r.R-$r.L), ($r.B-$r.T)))
    }
  }
  return $true }, [IntPtr]::Zero) | Out-Null
$global:found
