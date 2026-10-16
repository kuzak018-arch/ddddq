//! The overlay window: transparent, always on top, Acrylic blur of the game behind it,
//! click-through mode and global hotkeys (registered here in Rust so they work while
//! the game has focus and the main window is minimised).

use std::str::FromStr;
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, WebviewWindow};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};

pub const LABEL: &str = "overlay";

#[derive(Default)]
pub struct OverlayState {
    pub click_through: Mutex<bool>,
    pub hotkeys: Mutex<Hotkeys>,
}

#[derive(Clone, Default, Serialize, Deserialize)]
pub struct Hotkeys {
    pub toggle: String,
    pub interact: String,
}

#[derive(Clone, Serialize)]
struct OverlayStatus {
    visible: bool,
    click_through: bool,
}

fn window(app: &AppHandle) -> Result<WebviewWindow, String> {
    app.get_webview_window(LABEL).ok_or_else(|| "окно оверлея не найдено".to_string())
}

fn emit_status(app: &AppHandle) {
    if let Ok(w) = window(app) {
        let status = OverlayStatus {
            visible: w.is_visible().unwrap_or(false),
            click_through: *app.state::<OverlayState>().click_through.lock().unwrap(),
        };
        let _ = app.emit("overlay-status", status);
    }
}

pub fn toggle(app: &AppHandle) -> Result<(), String> {
    let w = window(app)?;
    if w.is_visible().map_err(|e| e.to_string())? {
        w.hide().map_err(|e| e.to_string())?;
    } else {
        w.show().map_err(|e| e.to_string())?;
        // keep focus in the game: the overlay is shown without stealing it
        let _ = w.set_always_on_top(true);
    }
    emit_status(app);
    Ok(())
}

pub fn set_click_through_inner(app: &AppHandle, on: bool) -> Result<(), String> {
    window(app)?.set_ignore_cursor_events(on).map_err(|e| e.to_string())?;
    *app.state::<OverlayState>().click_through.lock().unwrap() = on;
    emit_status(app);
    Ok(())
}

#[tauri::command]
pub fn overlay_toggle(app: AppHandle) -> Result<(), String> {
    toggle(&app)
}

#[tauri::command]
pub fn overlay_show(app: AppHandle, show: bool) -> Result<(), String> {
    let w = window(&app)?;
    if show { w.show() } else { w.hide() }.map_err(|e| e.to_string())?;
    emit_status(&app);
    Ok(())
}

#[tauri::command]
pub fn overlay_set_click_through(app: AppHandle, on: bool) -> Result<(), String> {
    set_click_through_inner(&app, on)
}

#[tauri::command]
pub fn overlay_status(app: AppHandle) -> Result<(bool, bool), String> {
    let w = window(&app)?;
    Ok((w.is_visible().unwrap_or(false), *app.state::<OverlayState>().click_through.lock().unwrap()))
}

/// "acrylic": the system blurs whatever is behind the window (the game); `alpha` is the tint.
/// "tint": no system effect, the page draws a darker translucent glass itself (performance mode,
/// or when Acrylic is unavailable). Returns the effect actually in use.
#[tauri::command]
pub fn overlay_set_effect(app: AppHandle, effect: String, alpha: u8) -> Result<String, String> {
    let w = window(&app)?;
    #[cfg(target_os = "windows")]
    {
        let _ = window_vibrancy::clear_acrylic(&w);
        if effect == "acrylic" {
            return match window_vibrancy::apply_acrylic(&w, Some((14, 15, 20, alpha))) {
                Ok(()) => Ok("acrylic".into()),
                Err(_) => Ok("tint".into()),
            };
        }
    }
    let _ = (&w, alpha);
    Ok("tint".into())
}

fn parse(s: &str) -> Result<Shortcut, String> {
    Shortcut::from_str(s).map_err(|e| format!("не понимаю сочетание «{s}»: {e}"))
}

/// Replace both global hotkeys. Fails without changing anything if a combo is invalid
/// or already taken by another program.
#[tauri::command]
pub fn overlay_set_hotkeys(app: AppHandle, toggle: String, interact: String) -> Result<(), String> {
    let (t, i) = (parse(&toggle)?, parse(&interact)?);
    if t == i {
        return Err("клавиши показа и сквозных кликов совпадают".into());
    }
    let gs = app.global_shortcut();
    let state = app.state::<OverlayState>();
    let old = state.hotkeys.lock().unwrap().clone();
    for s in [&old.toggle, &old.interact] {
        if let Ok(sc) = parse(s) {
            let _ = gs.unregister(sc);
        }
    }
    let register = |sc: Shortcut, label: &str| gs.register(sc).map_err(|e| format!("{label}: сочетание занято ({e})"));
    if let Err(e) = register(t, "показ оверлея").and_then(|_| register(i, "сквозные клики")) {
        let _ = gs.unregister(t);
        let _ = gs.unregister(i);
        for s in [&old.toggle, &old.interact] {
            if let Ok(sc) = parse(s) {
                let _ = gs.register(sc);
            }
        }
        return Err(e);
    }
    *state.hotkeys.lock().unwrap() = Hotkeys { toggle, interact };
    Ok(())
}

/// Global shortcut handler (installed once in lib.rs).
pub fn on_shortcut(app: &AppHandle, shortcut: &Shortcut, pressed: ShortcutState) {
    if pressed != ShortcutState::Pressed {
        return;
    }
    let keys = app.state::<OverlayState>().hotkeys.lock().unwrap().clone();
    if parse(&keys.toggle).map(|s| &s == shortcut).unwrap_or(false) {
        let _ = toggle(app);
    } else if parse(&keys.interact).map(|s| &s == shortcut).unwrap_or(false) {
        let on = !*app.state::<OverlayState>().click_through.lock().unwrap();
        if let Ok(w) = window(app) {
            if !w.is_visible().unwrap_or(false) {
                let _ = w.show();
            }
        }
        let _ = set_click_through_inner(app, on);
    }
}
