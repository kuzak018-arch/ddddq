//! Desktop shell: starts the Python backend on a free localhost port with a random
//! per-launch token, hands both to the UI, owns the overlay window and the global hotkeys,
//! and stops the backend when the app exits.

mod appicon;
mod backend;
mod overlay;
mod tray;

use std::sync::Mutex;
use tauri::{Manager, RunEvent, WindowEvent};
use tauri_plugin_window_state::StateFlags;

#[derive(Clone, serde::Serialize)]
struct BackendInfo {
    url: String,
    token: String,
    /// Where the backend came from: "external" (DRAFTER_API), "dev" (repo .venv) or "bundled".
    source: String,
}

/// Managed from the very start: a window can load and ask for the backend before `setup` has
/// started it (the release build serves the page from disk fast enough to win that race).
#[derive(Default)]
struct AppState {
    info: Mutex<Option<BackendInfo>>,
    child: Mutex<Option<std::process::Child>>,
}

#[tauri::command]
fn backend_info(state: tauri::State<'_, AppState>) -> Result<BackendInfo, String> {
    state.info.lock().unwrap().clone().ok_or_else(|| "бэкенд ещё запускается".to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| tray::show_main(app)))
        // autostart with Windows (off until the user turns it on): such a launch starts in the tray
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec![tray::MINIMIZED_ARG]),
        ))
        // remember size and position of both windows, but never re-open the overlay by itself
        .plugin(
            tauri_plugin_window_state::Builder::default()
                .with_state_flags(StateFlags::all() & !StateFlags::VISIBLE)
                .build(),
        )
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| overlay::on_shortcut(app, shortcut, event.state()))
                .build(),
        )
        .manage(overlay::OverlayState::default())
        .manage(AppState::default())
        .manage(tray::TrayState::default())
        .setup(|app| {
            tray::create(app.handle())?;
            appicon::restore(app.handle());
            if let Some(w) = app.get_webview_window(overlay::LABEL) {
                overlay::round_corners(&w);
            }
            if std::env::args().any(|a| a == tray::MINIMIZED_ARG) {
                if let Some(w) = app.get_webview_window("main") {
                    let _ = w.hide();
                }
            }
            let (info, child) = backend::start(app.path().resource_dir().ok())?;
            let state = app.state::<AppState>();
            *state.info.lock().unwrap() = Some(info);
            *state.child.lock().unwrap() = child;
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == overlay::LABEL
                && matches!(event, WindowEvent::Resized(_) | WindowEvent::ScaleFactorChanged { .. })
            {
                if let Some(w) = window.app_handle().get_webview_window(overlay::LABEL) {
                    overlay::round_corners(&w);
                }
            }
            // closing the main window quits the app (the hidden overlay must not keep it alive),
            // or hides it into the tray when the user chose that
            if window.label() == "main" {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    if tray::on_close(window.app_handle()) {
                        api.prevent_close();
                    } else {
                        window.app_handle().exit(0);
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            backend_info,
            overlay::overlay_toggle,
            overlay::overlay_show,
            overlay::overlay_set_click_through,
            overlay::overlay_status,
            overlay::overlay_set_effect,
            overlay::overlay_set_hotkeys,
            tray::set_close_to_tray,
            appicon::app_icon_state,
            appicon::set_app_icon,
        ])
        .build(tauri::generate_context!())
        .expect("не удалось запустить приложение");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(state) = handle.try_state::<AppState>() {
                if let Some(mut child) = state.child.lock().unwrap().take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        }
    });
}
