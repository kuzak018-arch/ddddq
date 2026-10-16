//! Locating and launching the Python API.
//!
//! Order: DRAFTER_API (+ DRAFTER_TOKEN) env -> an already running external backend;
//! `backend/drafter-backend.exe` in the app's resources -> the installed build;
//! otherwise the repository's `.venv` (development).

use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};

use crate::BackendInfo;

#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

fn random_token() -> String {
    let mut buf = [0u8; 24];
    getrandom::fill(&mut buf).expect("нет источника случайных чисел");
    buf.iter().map(|b| format!("{b:02x}")).collect()
}

fn free_port() -> std::io::Result<u16> {
    Ok(TcpListener::bind("127.0.0.1:0")?.local_addr()?.port())
}

fn repo_root() -> Option<PathBuf> {
    if let Ok(root) = std::env::var("DRAFTER_ROOT") {
        return Some(PathBuf::from(root));
    }
    // app/src-tauri -> repository root (development builds only)
    let manifest = Path::new(env!("CARGO_MANIFEST_DIR"));
    manifest.parent()?.parent().map(Path::to_path_buf).filter(|p| p.join("backend").is_dir())
}

fn spawn(mut cmd: Command, log: &Path) -> std::io::Result<Child> {
    if let Some(dir) = log.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let out = std::fs::File::create(log)?;
    cmd.stdout(Stdio::from(out.try_clone()?)).stderr(Stdio::from(out)).stdin(Stdio::null());
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    cmd.env("PYTHONIOENCODING", "utf-8");
    // write the log line by line: a block-buffered log hides the last requests when debugging
    cmd.env("PYTHONUNBUFFERED", "1");
    cmd.spawn()
}

/// Where the installed app keeps its writable files (the backend uses the same folder).
fn user_dir() -> PathBuf {
    std::env::var_os("LOCALAPPDATA").map(PathBuf::from).unwrap_or_default().join("DotaDrafter")
}

pub fn start(resource_dir: Option<PathBuf>) -> Result<(BackendInfo, Option<Child>), Box<dyn std::error::Error>> {
    if let Ok(url) = std::env::var("DRAFTER_API") {
        let token = std::env::var("DRAFTER_TOKEN").unwrap_or_default();
        return Ok((BackendInfo { url, token, source: "external".into() }, None));
    }
    let port = free_port()?;
    let token = random_token();
    let url = format!("http://127.0.0.1:{port}");
    let args = ["--port".to_string(), port.to_string(), "--token".to_string(), token.clone()];

    // debug builds (tauri dev) run the backend from source even if a bundled copy was built
    let prefer_source = cfg!(debug_assertions) && repo_root().is_some();
    let bundled = resource_dir.map(|d| d.join("backend").join("drafter-backend.exe")).filter(|p| p.exists());
    if let Some(bundled) = bundled.filter(|_| !prefer_source) {
        let mut cmd = Command::new(&bundled);
        cmd.args(args).current_dir(bundled.parent().unwrap_or(Path::new(".")));
        let child = spawn(cmd, &user_dir().join("logs").join("backend.log"))?;
        return Ok((BackendInfo { url, token, source: "bundled".into() }, Some(child)));
    }

    let root = repo_root().ok_or("не найден бэкенд: нет drafter-backend.exe и репозитория")?;
    let python = root.join(".venv").join("Scripts").join("python.exe");
    let mut cmd = Command::new(&python);
    cmd.args(["-m", "drafter.api"]).args(args).current_dir(root.join("backend"));
    let child = spawn(cmd, &root.join("data").join("api.log"))?;
    Ok((BackendInfo { url, token, source: "dev".into() }, Some(child)))
}
