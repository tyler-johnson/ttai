// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::sync::Arc;
use tauri::Manager;
use tokio::sync::Mutex;
use ttai_lib::commands::AppState;
use ttai_lib::sidecar::SidecarManager;

fn main() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Get path to src-python directory (relative to src-tauri)
            let python_path = app
                .path()
                .resource_dir()
                .map(|p| p.join("../src-python"))
                .unwrap_or_else(|_| PathBuf::from("../src-python"));

            // In development, use the actual source path
            let python_path = if cfg!(debug_assertions) {
                PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../src-python")
            } else {
                python_path
            };

            log::info!("Python path: {:?}", python_path);

            let manager = SidecarManager::new(python_path);
            let state: AppState = Arc::new(Mutex::new(manager));

            app.manage(state.clone());

            // Auto-start the server
            let state_clone = state.clone();
            tauri::async_runtime::spawn(async move {
                let manager = state_clone.lock().await;
                if let Err(e) = manager.start() {
                    log::error!("Failed to auto-start server: {}", e);
                    return;
                }

                // Wait for HTTP server to be ready
                if let Err(e) = manager.wait_for_ready().await {
                    log::error!("Server failed to become ready: {}", e);
                } else {
                    log::info!("Server auto-started and ready");
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                log::info!("Window close requested, stopping sidecar...");
                let state = window.state::<AppState>();
                let state_clone = state.inner().clone();
                tauri::async_runtime::block_on(async move {
                    let manager = state_clone.lock().await;
                    if let Err(e) = manager.stop() {
                        log::error!("Failed to stop server: {}", e);
                    }
                });
            }
        })
        .invoke_handler(tauri::generate_handler![
            ttai_lib::commands::start_server,
            ttai_lib::commands::stop_server,
            ttai_lib::commands::is_server_running,
            ttai_lib::commands::reconnect_server,
            ttai_lib::commands::mcp_ping,
            ttai_lib::commands::mcp_login,
            ttai_lib::commands::mcp_logout,
            ttai_lib::commands::mcp_get_auth_status,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
