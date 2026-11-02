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
    /// the effect and tint last applied, and whether the window has its shadow (rounded corners)
    effect: Mutex<Option<(String, u8)>>,
    shadow: Mutex<bool>,
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

pub fn emit_status(app: &AppHandle) {
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
        show_keeping_focus(&w)?;
        let _ = w.set_always_on_top(true);
    }
    emit_status(app);
    Ok(())
}

/// Shows the overlay and gives the focus back to the window that had it (the game): showing a
/// window activates it, and the game would lose the keyboard (or minimise in exclusive fullscreen).
fn show_keeping_focus(w: &WebviewWindow) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        use windows_sys::Win32::UI::WindowsAndMessaging::{GetForegroundWindow, SetForegroundWindow};
        let before = unsafe { GetForegroundWindow() };
        w.show().map_err(|e| e.to_string())?;
        let own = w.hwnd().map(|h| h.0 as isize).unwrap_or(0);
        if !before.is_null() && before as isize != own {
            unsafe { SetForegroundWindow(before) };
        }
        Ok(())
    }
    #[cfg(not(target_os = "windows"))]
    w.show().map_err(|e| e.to_string())
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
    if show { show_keeping_focus(&w) } else { w.hide().map_err(|e| e.to_string()) }?;
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
/// or when Acrylic is unavailable). Returns the effect actually in use. Applying the same effect
/// again is skipped (re-applying Acrylic makes the window flash).
#[tauri::command]
pub fn overlay_set_effect(app: AppHandle, effect: String, alpha: u8) -> Result<String, String> {
    let w = window(&app)?;
    let state = app.state::<OverlayState>();
    if let Some((used, a)) = state.effect.lock().unwrap().clone() {
        if (used == effect && a == alpha) || (used == "tint" && effect == "tint") {
            return Ok(used);
        }
    }
    let mut used = "tint".to_string();
    #[cfg(target_os = "windows")]
    {
        let _ = window_vibrancy::clear_acrylic(&w);
        if effect == "acrylic" && window_vibrancy::apply_acrylic(&w, Some((14, 15, 20, alpha))).is_ok() {
            used = "acrylic".into();
        }
        round_corners(&app, &w, used == "acrylic");
    }
    let _ = (&w, alpha);
    *state.effect.lock().unwrap() = Some((used.clone(), alpha));
    Ok(used)
}

/// Acrylic fills the whole window rectangle, so its corners must be rounded by Windows itself: an
/// undecorated window with a shadow keeps the system frame (tao trims it in WM_NCCALCSIZE), and
/// Windows 11 rounds such windows (8 px; the page's panel uses the same radius, overlay.css). The
/// thin system border is turned off. With the plain tint the page draws everything, so no shadow:
/// the transparent corners stay invisible and the panel keeps its own larger rounding. (A window
/// region, SetWindowRgn, must not be used: it switches the window to the classic frame — an
/// XP-style title bar.) Turning the shadow on or off changes the frame insets, so the page's size
/// and place are put back (else the overlay shrank by the frame on every start).
#[cfg(target_os = "windows")]
fn round_corners(app: &AppHandle, w: &WebviewWindow, on: bool) {
    use tauri::PhysicalPosition;
    use windows_sys::Win32::Graphics::Dwm::{
        DwmSetWindowAttribute, DWMWA_BORDER_COLOR, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DEFAULT, DWMWCP_ROUND,
    };
    const COLOR_NONE: u32 = 0xFFFF_FFFE;
    const COLOR_DEFAULT: u32 = 0xFFFF_FFFF;
    let state = app.state::<OverlayState>();
    let mut shadow = state.shadow.lock().unwrap();
    if *shadow != on {
        let (size, before) = (w.inner_size().ok(), w.inner_position().ok());
        let _ = w.set_shadow(on);
        if let Some(size) = size {
            let _ = w.set_size(size);
        }
        if let (Some(before), Ok(after), Ok(outer)) = (before, w.inner_position(), w.outer_position()) {
            if before != after {
                let _ = w.set_position(PhysicalPosition::new(outer.x + before.x - after.x, outer.y + before.y - after.y));
            }
        }
        *shadow = on;
    }
    if let Ok(hwnd) = w.hwnd() {
        let pref = if on { DWMWCP_ROUND } else { DWMWCP_DEFAULT };
        let border = if on { COLOR_NONE } else { COLOR_DEFAULT };
        // Windows 10 has neither attribute and returns an error: the corners just stay square there
        unsafe {
            DwmSetWindowAttribute(hwnd.0 as _, DWMWA_WINDOW_CORNER_PREFERENCE as u32, (&pref as *const i32).cast(), 4);
            DwmSetWindowAttribute(hwnd.0 as _, DWMWA_BORDER_COLOR as u32, (&border as *const u32).cast(), 4);
        }
    }
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
                let _ = show_keeping_focus(&w);
                let _ = w.set_always_on_top(true);
            }
        }
        let _ = set_click_through_inner(app, on);
    }
}
