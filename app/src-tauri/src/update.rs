//! Installing a downloaded update. The backend downloads the installer into
//! %LOCALAPPDATA%\DotaDrafter\data\updates and checks its SHA-256 (backend/drafter/updates.py);
//! here it runs over this version in passive mode (no wizard; settings and data stay), and the app
//! quits so its files can be replaced. Right away, with `/R` (the new version starts when the
//! installer is done), or when the app is closed next time (automatic updates).

use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

use tauri::{AppHandle, Manager};

#[derive(Default)]
pub struct UpdateState {
    pending: Mutex<Option<PathBuf>>,
    /// the user quit (tray «Выход», closing the main window): only then the pending update runs —
    /// not when Windows shuts down or a Restart Manager closes the app (the installer would be
    /// killed half-way or race another one)
    user_quit: AtomicBool,
}

/// Called right before the app quits at the user's request.
pub fn mark_user_quit(app: &AppHandle) {
    if let Some(state) = app.try_state::<UpdateState>() {
        state.user_quit.store(true, Ordering::Relaxed);
    }
}

/// Only an installer of ours, straight from the updates folder.
fn checked(path: &str) -> Result<PathBuf, String> {
    let real = std::fs::canonicalize(path).map_err(|_| "файла обновления нет".to_string())?;
    let dir = std::env::var_os("LOCALAPPDATA")
        .map(|d| PathBuf::from(d).join("DotaDrafter").join("data").join("updates"))
        .and_then(|d| std::fs::canonicalize(d).ok())
        .ok_or("папки обновлений нет")?;
    let name = real.file_name().and_then(|n| n.to_str()).unwrap_or("");
    if real.parent() != Some(dir.as_path()) || !name.starts_with("Dota") || !name.ends_with("_x64-setup.exe") {
        return Err("это не установщик обновления".into());
    }
    Ok(PathBuf::from(path))
}

fn run(exe: &PathBuf, relaunch: bool) -> Result<(), String> {
    let mut args = vec!["/P", "/UPDATE"];
    if relaunch {
        args.push("/R");
    }
    Command::new(exe).args(args).spawn().map(drop).map_err(|e| format!("не запустил установщик: {e}"))
}

#[tauri::command]
pub fn install_update(app: AppHandle, path: String) -> Result<(), String> {
    let exe = checked(&path)?;
    run(&exe, true)?;
    // started: no second run on exit (a failed start keeps the one armed for exit)
    app.state::<UpdateState>().pending.lock().unwrap().take();
    app.exit(0);
    Ok(())
}

/// The installer to run when the app quits (None: nothing).
#[tauri::command]
pub fn set_pending_update(app: AppHandle, path: Option<String>) -> Result<(), String> {
    let exe = path.as_deref().map(checked).transpose()?;
    *app.state::<UpdateState>().pending.lock().unwrap() = exe;
    Ok(())
}

/// On exit: the update waiting for it, if any (the new version is not started).
pub fn on_exit(app: &AppHandle) {
    if let Some(state) = app.try_state::<UpdateState>() {
        if !state.user_quit.load(Ordering::Relaxed) {
            return;
        }
        if let Some(exe) = state.pending.lock().unwrap().take() {
            if let Err(e) = run(&exe, false) {
                eprintln!("{e}");
            }
        }
    }
}
