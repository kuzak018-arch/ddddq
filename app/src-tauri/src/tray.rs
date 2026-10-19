//! The tray icon: show the window, overlay on/off, quit. With «сворачивать в трей» on, closing the
//! main window hides it here instead of quitting; a launch with `--minimized` (autostart with
//! Windows) starts in the tray.

use std::sync::atomic::{AtomicBool, Ordering};

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager};

use crate::overlay;

/// Close the main window to the tray instead of quitting (set from the UI's settings).
#[derive(Default)]
pub struct TrayState {
    pub close_to_tray: AtomicBool,
}

pub const MINIMIZED_ARG: &str = "--minimized";

pub fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

pub fn create(app: &AppHandle) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "Показать окно", true, None::<&str>)?;
    let overlay = MenuItem::with_id(app, "overlay", "Оверлей вкл/выкл", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Выход", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &overlay, &PredefinedMenuItem::separator(app)?, &quit])?;
    let mut tray = TrayIconBuilder::with_id("main")
        .tooltip("Dota Drafter")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => show_main(app),
            "overlay" => {
                let _ = overlay::toggle(app);
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            // a left click brings the window back; the right click opens the menu
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                show_main(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        tray = tray.icon(icon.clone());
    }
    tray.build(app)?;
    Ok(())
}

/// Closing the main window: hide it into the tray when the user wants that, else quit the app.
/// Returns whether the window was hidden (the close must then be prevented).
pub fn on_close(app: &AppHandle) -> bool {
    let to_tray = app.state::<TrayState>().close_to_tray.load(Ordering::Relaxed);
    if to_tray {
        if let Some(w) = app.get_webview_window("main") {
            let _ = w.hide();
        }
    }
    to_tray
}

#[tauri::command]
pub fn set_close_to_tray(state: tauri::State<'_, TrayState>, on: bool) {
    state.close_to_tray.store(on, Ordering::Relaxed);
}
