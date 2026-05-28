"""Windows UI Automation bridge for native app context and basic control."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from core.config import config_value


def context_summary(limit: int | None = None) -> dict[str, Any]:
    if not bool(config_value("app_accessibility_enabled", True)):
        return {"available": False, "reason": "app_accessibility_disabled"}
    max_nodes = max(5, min(120, int(limit or config_value("app_accessibility_max_nodes", 60))))
    script = _context_script(max_nodes)
    return _run_json_script(script, timeout=float(config_value("app_accessibility_timeout_seconds", 2.5)))


def execute_uia_action(action: dict[str, Any]) -> str:
    name = str(action.get("action") or "").strip().lower()
    if name not in {"uia_invoke", "uia_focus", "uia_set_text"}:
        return "UI Automation action is unsupported."
    script = _action_script(action)
    result = _run_json_script(script, timeout=float(config_value("app_accessibility_timeout_seconds", 2.5)))
    if result.get("ok"):
        return str(result.get("message") or "UI Automation action completed.")
    return f"UI Automation action failed: {result.get('reason', 'element not found')}"


def _run_json_script(script: str, *, timeout: float) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return {"available": False, "reason": str(exc), "elements": []}
    raw = (completed.stdout or completed.stderr or "").strip()
    try:
        data = json.loads(raw)
    except Exception:
        return {"available": False, "reason": raw[:300] or "uia_json_parse_failed", "elements": []}
    return data if isinstance(data, dict) else {"available": False, "reason": "uia_invalid_payload", "elements": []}


def _context_script(max_nodes: int) -> str:
    return rf"""
Add-Type -AssemblyName UIAutomationClient
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {{
  [DllImport("user32.dll")]
  public static extern IntPtr GetForegroundWindow();
}}
"@
$hwnd = [Win32]::GetForegroundWindow()
if ($hwnd -eq [IntPtr]::Zero) {{ @{{available=$false; reason="no_foreground_window"; elements=@()}} | ConvertTo-Json -Depth 6; exit }}
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
if ($null -eq $root) {{ @{{available=$false; reason="automation_root_missing"; elements=@()}} | ConvertTo-Json -Depth 6; exit }}
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$queue = New-Object System.Collections.Queue
$queue.Enqueue(@($root, 0))
$items = @()
while ($queue.Count -gt 0 -and $items.Count -lt {max_nodes}) {{
  $pair = $queue.Dequeue()
  $el = $pair[0]
  $depth = [int]$pair[1]
  try {{
    $rect = $el.Current.BoundingRectangle
    $typeName = $el.Current.ControlType.ProgrammaticName -replace '^ControlType\.',''
    $patterns = @()
    foreach ($p in $el.GetSupportedPatterns()) {{ $patterns += ($p.ProgrammaticName -replace '^PatternIdentifiers\.','') }}
    $items += [pscustomobject]@{{
      depth=$depth
      name=[string]$el.Current.Name
      automation_id=[string]$el.Current.AutomationId
      control_type=$typeName
      enabled=[bool]$el.Current.IsEnabled
      rect=@{{x=[int]$rect.X; y=[int]$rect.Y; w=[int]$rect.Width; h=[int]$rect.Height}}
      patterns=$patterns
    }}
    if ($depth -lt 3) {{
      $child = $walker.GetFirstChild($el)
      while ($null -ne $child -and $items.Count -lt {max_nodes}) {{
        $queue.Enqueue(@($child, $depth + 1))
        $child = $walker.GetNextSibling($child)
      }}
    }}
  }} catch {{}}
}}
$text = ($items | ForEach-Object {{ "$($_.name) $($_.automation_id) $($_.control_type)" }}) -join " "
$detections = @()
if ($text -match '(?i)captcha|verify.*human|not.*robot') {{ $detections += "captcha" }}
if (($text -match '(?i)password|username|verification code') -and ($text -match '(?i)sign in|log in|login|account')) {{ $detections += "login" }}
@{{
  available=$true
  window_name=[string]$root.Current.Name
  window_class=[string]$root.Current.ClassName
  detections=$detections
  elements=$items
}} | ConvertTo-Json -Depth 8 -Compress
"""


def _action_script(action: dict[str, Any]) -> str:
    action_name = str(action.get("action") or "")
    name = str(action.get("name") or action.get("target") or "")
    automation_id = str(action.get("automation_id") or "")
    control_type = str(action.get("control_type") or "")
    value = str(action.get("value") or action.get("text") or "")
    return rf"""
Add-Type -AssemblyName UIAutomationClient
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {{
  [DllImport("user32.dll")]
  public static extern IntPtr GetForegroundWindow();
}}
"@
$hwnd = [Win32]::GetForegroundWindow()
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
if ($null -eq $root) {{ @{{ok=$false; reason="automation_root_missing"}} | ConvertTo-Json -Compress; exit }}
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$queue = New-Object System.Collections.Queue
$queue.Enqueue($root)
$match = $null
while ($queue.Count -gt 0 -and $null -eq $match) {{
  $el = $queue.Dequeue()
  try {{
    $elName = [string]$el.Current.Name
    $elId = [string]$el.Current.AutomationId
    $elType = [string]($el.Current.ControlType.ProgrammaticName -replace '^ControlType\.','')
    $ok = $true
    if ({json.dumps(name)} -ne "" -and $elName -notlike ("*" + {json.dumps(name)} + "*")) {{ $ok = $false }}
    if ({json.dumps(automation_id)} -ne "" -and $elId -ne {json.dumps(automation_id)}) {{ $ok = $false }}
    if ({json.dumps(control_type)} -ne "" -and $elType -ne {json.dumps(control_type)}) {{ $ok = $false }}
    if ($ok) {{ $match = $el; break }}
    $child = $walker.GetFirstChild($el)
    while ($null -ne $child) {{
      $queue.Enqueue($child)
      $child = $walker.GetNextSibling($child)
    }}
  }} catch {{}}
}}
if ($null -eq $match) {{ @{{ok=$false; reason="element_not_found"}} | ConvertTo-Json -Compress; exit }}
try {{
  if ({json.dumps(action_name)} -eq "uia_focus") {{
    $match.SetFocus()
    @{{ok=$true; message="UI element focused."}} | ConvertTo-Json -Compress; exit
  }}
  if ({json.dumps(action_name)} -eq "uia_set_text") {{
    $pattern = $match.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    $pattern.SetValue({json.dumps(value)})
    @{{ok=$true; message="UI element text set."}} | ConvertTo-Json -Compress; exit
  }}
  $invoke = $match.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
  $invoke.Invoke()
  @{{ok=$true; message="UI element invoked."}} | ConvertTo-Json -Compress
}} catch {{
  @{{ok=$false; reason=$_.Exception.Message}} | ConvertTo-Json -Compress
}}
"""
