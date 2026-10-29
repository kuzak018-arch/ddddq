//! The user's own app icon everywhere Windows lets us change it: every window (taskbar, Alt+Tab),
//! the tray, and our shortcuts on the desktop, in the Start menu and pinned to the taskbar (an
//! .ico in the data folder set as their icon). The icon inside the .exe cannot change.
//!
//! The UI makes the PNG and the .ico from the picture and hands them over once; they are kept in
//! %LOCALAPPDATA%\DotaDrafter\icon and put back at every start (an update reinstalls the shortcuts
//! with the built-in icon).

use std::fs;
use std::path::{Path, PathBuf};

use serde::Serialize;
use tauri::image::Image;
use tauri::{AppHandle, Manager};

const PNG: &str = "app-icon.png";
const KEY: &str = "key.txt";

fn dir() -> PathBuf {
    crate::backend::user_dir().join("icon")
}

#[derive(Serialize)]
pub struct IconState {
    /// The UI's key of the picture now in use, None for the built-in icon.
    key: Option<String>,
}

#[derive(Serialize)]
pub struct Applied {
    /// "Рабочий стол", "Пуск", "Панель задач" — where a shortcut of ours got the icon.
    shortcuts: Vec<String>,
    /// Shortcuts that could not be changed (or why none were looked at).
    error: Option<String>,
}

/// The newest .ico in the folder (its name changes with each picture, so Explorer's icon cache
/// cannot show the previous one).
fn current_ico() -> Option<PathBuf> {
    let mut icos: Vec<_> = fs::read_dir(dir())
        .ok()?
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.extension().is_some_and(|x| x == "ico"))
        .collect();
    icos.sort();
    icos.pop()
}

fn apply_windows(app: &AppHandle, png: Option<&[u8]>) {
    let custom = png.and_then(|b| Image::from_bytes(b).ok()).map(|i| i.to_owned());
    let Some(icon) = custom.or_else(|| app.default_window_icon().map(|i| i.clone().to_owned())) else { return };
    for w in app.webview_windows().values() {
        let _ = w.set_icon(icon.clone());
    }
    if let Some(tray) = app.tray_by_id("main") {
        let _ = tray.set_icon(Some(icon));
    }
}

/// At start: the saved picture on every window and the tray, the shortcuts checked in the
/// background.
pub fn restore(app: &AppHandle) {
    let Ok(png) = fs::read(dir().join(PNG)) else { return };
    apply_windows(app, Some(&png));
    if let Some(ico) = current_ico() {
        std::thread::spawn(move || {
            let _ = shortcuts::update(Some(&ico));
        });
    }
}

#[tauri::command]
pub fn app_icon_state() -> IconState {
    let key = fs::read_to_string(dir().join(KEY)).ok().filter(|_| dir().join(PNG).exists());
    IconState { key }
}

/// `png` and `ico` of the picture, or neither for the built-in icon.
#[tauri::command]
pub async fn set_app_icon(app: AppHandle, png: Option<Vec<u8>>, ico: Option<Vec<u8>>, key: Option<String>) -> Result<Applied, String> {
    let d = dir();
    fs::create_dir_all(&d).map_err(|e| e.to_string())?;
    if let Some(png) = &png {
        // checked before the folder is cleared: a bad picture must not cost the icon already set
        if Image::from_bytes(png).is_err() {
            return Err("картинка значка не читается".into());
        }
    }
    for e in fs::read_dir(&d).map_err(|e| e.to_string())?.flatten() {
        let _ = fs::remove_file(e.path());
    }
    let ico_path = match (&png, &ico) {
        (Some(png), Some(ico)) => {
            fs::write(d.join(PNG), png).map_err(|e| e.to_string())?;
            let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|t| t.as_millis()).unwrap_or(0);
            let p = d.join(format!("app-icon-{stamp}.ico"));
            fs::write(&p, ico).map_err(|e| e.to_string())?;
            fs::write(d.join(KEY), key.unwrap_or_default()).map_err(|e| e.to_string())?;
            Some(p)
        }
        _ => None,
    };
    apply_windows(&app, png.as_deref());
    tauri::async_runtime::spawn_blocking(move || shortcuts::update(ico_path.as_deref()))
        .await
        .map_err(|e| e.to_string())
}

/// Standard base64 (PowerShell's -EncodedCommand), kept here to avoid a crate for 20 lines.
#[cfg_attr(not(windows), allow(dead_code))]
fn base64(data: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut s = String::with_capacity(data.len().div_ceil(3) * 4);
    for c in data.chunks(3) {
        let n = (c[0] as u32) << 16 | (*c.get(1).unwrap_or(&0) as u32) << 8 | *c.get(2).unwrap_or(&0) as u32;
        for i in 0..4 {
            s.push(if i <= c.len() { T[(n >> (18 - 6 * i) & 63) as usize] as char } else { '=' });
        }
    }
    s
}

#[cfg(test)]
mod tests {
    #[test]
    fn base64_matches_known_values() {
        assert_eq!(super::base64(b""), "");
        assert_eq!(super::base64(b"f"), "Zg==");
        assert_eq!(super::base64(b"fo"), "Zm8=");
        assert_eq!(super::base64(b"foo"), "Zm9v");
        assert_eq!(super::base64(b"foobar"), "Zm9vYmFy");
    }
}

#[cfg(windows)]
mod shortcuts {
    use super::{Applied, Path, base64};
    use std::os::windows::process::CommandExt;
    use std::process::Command;

    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    const PLACES: [&str; 3] = ["Рабочий стол", "Пуск", "Панель задач"];

    /// Our shortcuts are the .lnk files whose target is this exe, wherever the user keeps them in
    /// the three folders. PowerShell's WScript.Shell sets their icon; the script is passed
    /// UTF-16 encoded, so paths with Cyrillic letters survive.
    pub fn update(ico: Option<&Path>) -> Applied {
        let exe = match std::env::current_exe() {
            Ok(p) => p,
            Err(e) => return Applied { shortcuts: vec![], error: Some(e.to_string()) },
        };
        let q = |p: &Path| p.display().to_string().replace('\'', "''");
        let location = format!("{},0", q(ico.unwrap_or(&exe)));
        let script = format!(
            r#"[Console]::OutputEncoding = [Text.Encoding]::UTF8
$exe = [IO.Path]::GetFullPath('{exe}')
$loc = '{location}'
$sh = New-Object -ComObject WScript.Shell
$dirs = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'), (Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'))
for ($i = 0; $i -lt $dirs.Count; $i++) {{
  $d = $dirs[$i]
  if (-not $d -or -not (Test-Path -LiteralPath $d)) {{ continue }}
  Get-ChildItem -LiteralPath $d -Filter *.lnk -Recurse -Depth 2 -ErrorAction SilentlyContinue | ForEach-Object {{
    try {{
      $l = $sh.CreateShortcut($_.FullName)
      if ($l.TargetPath -and ([IO.Path]::GetFullPath($l.TargetPath) -ieq $exe)) {{
        if ($l.IconLocation -ne $loc) {{ $l.IconLocation = $loc; $l.Save() }}
        "OK|$i"
      }}
    }} catch {{ "FAIL|$i|" + $_.Exception.Message }}
  }}
}}"#,
            exe = q(&exe),
        );
        let utf16: Vec<u8> = script.encode_utf16().flat_map(|c| c.to_le_bytes()).collect();
        let out = Command::new("powershell.exe")
            .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", &base64(&utf16)])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
        let out = match out {
            Ok(o) => String::from_utf8_lossy(&o.stdout).into_owned(),
            Err(e) => return Applied { shortcuts: vec![], error: Some(format!("PowerShell не запустился: {e}")) },
        };
        let mut shortcuts = Vec::new();
        let mut failed = Vec::new();
        for line in out.lines() {
            let parts: Vec<&str> = line.trim().splitn(3, '|').collect();
            let place = parts.get(1).and_then(|i| i.parse::<usize>().ok()).and_then(|i| PLACES.get(i)).copied();
            match (parts.first().copied(), place) {
                (Some("OK"), Some(p)) if !shortcuts.contains(&p.to_string()) => shortcuts.push(p.to_string()),
                (Some("FAIL"), Some(p)) => failed.push(format!("{p}: {}", parts.get(2).unwrap_or(&""))),
                _ => {}
            }
        }
        refresh_shell();
        let error = (!failed.is_empty()).then(|| format!("не удалось изменить ярлык — {}", failed.join("; ")));
        Applied { shortcuts, error }
    }

    /// Tell Explorer the icons changed, so the desktop and the taskbar redraw them.
    fn refresh_shell() {
        use windows_sys::Win32::UI::Shell::{SHCNE_ASSOCCHANGED, SHCNF_IDLIST, SHChangeNotify};
        unsafe { SHChangeNotify(SHCNE_ASSOCCHANGED as _, SHCNF_IDLIST, std::ptr::null(), std::ptr::null()) };
    }
}

#[cfg(not(windows))]
mod shortcuts {
    use super::{Applied, Path};

    pub fn update(_ico: Option<&Path>) -> Applied {
        Applied { shortcuts: vec![], error: Some("ярлыки меняются только в Windows".into()) }
    }
}
