//! Desktop shell: starts the Python backend on a free localhost port with a random
//! per-launch token, hands both to the UI, owns the overlay window and the global hotkeys,
//! and stops the backend when the app exits.

mod appicon;
mod backend;
mod overlay;
mod tray;
mod update;

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
    /// why the backend did not start (shown by the UI instead of the app vanishing)
    error: Mutex<Option<String>>,
    child: Mutex<Option<std::process::Child>>,
}

#[tauri::command]
fn backend_info(state: tauri::State<'_, AppState>) -> Result<BackendInfo, String> {
    if let Some(e) = state.error.lock().unwrap().clone() {
        return Err(e);
    }
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
        .manage(update::UpdateState::default())
        .setup(|app| {
            // an error here must not end the app silently (setup errors abort it with no message)
            if let Err(e) = tray::create(app.handle()) {
                eprintln!("значок в трее не создан: {e}");
            }
            appicon::restore(app.handle());
            // the main window starts hidden (tauri.conf): shown here unless launched into the tray
            if !std::env::args().any(|a| a == tray::MINIMIZED_ARG) {
                if let Some(w) = app.get_webview_window("main") {
                    let _ = w.show();
                }
            }
            let state = app.state::<AppState>();
            match backend::start(app.path().resource_dir().ok()) {
                Ok((info, child)) => {
                    *state.info.lock().unwrap() = Some(info);
                    *state.child.lock().unwrap() = child;
                }
                Err(e) => *state.error.lock().unwrap() = Some(format!("не удалось запустить бэкенд: {e}")),
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // closing the main window quits the app (the hidden overlay must not keep it alive),
            // or hides it into the tray when the user chose that
            if window.label() == "main" {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    if tray::on_close(window.app_handle()) {
                        api.prevent_close();
                    } else {
                        update::mark_user_quit(window.app_handle());
                        window.app_handle().exit(0);
                    }
                }
            }
            // Alt+F4 on the overlay would destroy it until the next start: it is only hidden
            if window.label() == overlay::LABEL {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window.hide();
                    overlay::emit_status(window.app_handle());
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
            update::install_update,
            update::set_pending_update,
        ])
        .build(tauri::generate_context!())
        .expect("не удалось запустить приложение");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            update::on_exit(handle);
            if let Some(state) = handle.try_state::<AppState>() {
                if let Some(mut child) = state.child.lock().unwrap().take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        }
    });
}
