use crate::sidecar::SidecarManager;
use serde_json::{json, Value};
use std::sync::Arc;
use tauri::State;
use tokio::sync::Mutex;

pub type AppState = Arc<Mutex<SidecarManager>>;

#[tauri::command]
pub async fn start_server(state: State<'_, AppState>) -> Result<(), String> {
    let manager = state.lock().await;
    manager.start()
}

#[tauri::command]
pub async fn stop_server(state: State<'_, AppState>) -> Result<(), String> {
    let manager = state.lock().await;
    manager.stop()
}

#[tauri::command]
pub async fn is_server_running(state: State<'_, AppState>) -> Result<bool, String> {
    let manager = state.lock().await;
    Ok(manager.is_running())
}

#[tauri::command]
pub async fn reconnect_server(state: State<'_, AppState>) -> Result<(), String> {
    let manager = state.lock().await;

    // Stop if running
    let _ = manager.stop();

    // Start fresh
    manager.start()?;
    manager.wait_for_ready().await?;

    Ok(())
}

#[tauri::command]
pub async fn mcp_ping(state: State<'_, AppState>) -> Result<String, String> {
    let manager = state.lock().await;
    manager.health_check().await?;
    Ok("pong".to_string())
}

#[tauri::command]
pub async fn mcp_login(
    state: State<'_, AppState>,
    client_secret: String,
    refresh_token: String,
    remember_me: bool,
) -> Result<Value, String> {
    let manager = state.lock().await;
    let result = manager
        .login(&client_secret, &refresh_token, remember_me)
        .await?;

    Ok(json!({
        "success": result.success,
        "error": result.error,
    }))
}

#[tauri::command]
pub async fn mcp_logout(state: State<'_, AppState>, clear_credentials: bool) -> Result<Value, String> {
    let manager = state.lock().await;
    let result = manager.logout(clear_credentials).await?;

    Ok(json!({
        "success": result.success,
    }))
}

#[tauri::command]
pub async fn mcp_get_auth_status(state: State<'_, AppState>) -> Result<Value, String> {
    let manager = state.lock().await;
    let status = manager.get_auth_status().await?;

    Ok(json!({
        "authenticated": status.authenticated,
        "has_stored_credentials": status.has_stored_credentials,
    }))
}
