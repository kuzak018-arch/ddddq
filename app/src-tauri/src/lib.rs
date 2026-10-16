//! Desktop shell: starts the Python backend on a free localhost port with a random
//! per-launch token, hands both to the UI, and stops the backend when the app exits.

mod backend;

use std::sync::Mutex;
use tauri::{Manager, RunEvent};

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
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .setup(|app| {
            let (info, child) = backend::start()?;
            app.manage(AppState { info, child: Mutex::new(child) });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_info])
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
