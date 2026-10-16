//! Desktop shell: starts the Python backend on a free localhost port with a random
//! per-launch token, hands both to the UI, owns the overlay window and the global hotkeys,
//! and stops the backend when the app exits.

mod backend;
mod overlay;

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

struct AppState {
    info: BackendInfo,
    child: Mutex<Option<std::process::Child>>,
}

#[tauri::command]
fn backend_info(state: tauri::State<'_, AppState>) -> BackendInfo {
    state.info.clone()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.set_focus();
            }
        }))
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
        .setup(|app| {
            let (info, child) = backend::start()?;
            app.manage(AppState { info, child: Mutex::new(child) });
            Ok(())
        })
        .on_window_event(|window, event| {
            // closing the main window quits the app (the hidden overlay must not keep it alive)
            if window.label() == "main" {
                if let WindowEvent::CloseRequested { .. } = event {
                    window.app_handle().exit(0);
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
