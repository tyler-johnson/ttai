use serde::Deserialize;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::Duration;

#[derive(Debug, Deserialize)]
pub struct AuthStatus {
    pub authenticated: bool,
    pub has_stored_credentials: bool,
}

#[derive(Debug, Deserialize)]
pub struct LoginResponse {
    pub success: bool,
    pub error: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct LogoutResponse {
    pub success: bool,
    pub error: Option<String>,
}

pub struct SidecarManager {
    child: Arc<Mutex<Option<Child>>>,
    python_path: PathBuf,
    http_client: reqwest::Client,
    base_url: String,
}

impl SidecarManager {
    pub fn new(python_path: PathBuf) -> Self {
        Self {
            child: Arc::new(Mutex::new(None)),
            python_path,
            http_client: reqwest::Client::new(),
            base_url: "http://localhost:8080".to_string(),
        }
    }

    pub fn start(&self) -> Result<(), String> {
        let mut child_guard = self.child.lock().map_err(|e| e.to_string())?;

        if child_guard.is_some() {
            return Err("Server already running".to_string());
        }

        log::info!("Starting Python MCP server at {:?}", self.python_path);

        let child = Command::new("uv")
            .args([
                "run",
                "python",
                "-m",
                "src.server.main",
                "--transport",
                "sse",
                "--port",
                "8080",
            ])
            .current_dir(&self.python_path)
            .stdin(Stdio::null())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|e| format!("Failed to spawn Python server: {}", e))?;

        *child_guard = Some(child);

        Ok(())
    }

    /// Wait for the HTTP server to be ready
    pub async fn wait_for_ready(&self) -> Result<(), String> {
        let max_attempts = 50;
        let delay = Duration::from_millis(100);

        for attempt in 0..max_attempts {
            if self.health_check().await.is_ok() {
                log::info!("MCP server ready after {} attempts", attempt + 1);
                return Ok(());
            }
            tokio::time::sleep(delay).await;
        }

        Err("Server failed to start".to_string())
    }

    /// Health check using REST API
    pub async fn health_check(&self) -> Result<(), String> {
        let url = format!("{}/api/health", self.base_url);

        let response = self
            .http_client
            .get(&url)
            .timeout(Duration::from_secs(2))
            .send()
            .await
            .map_err(|e| format!("Health check failed: {}", e))?;

        if response.status().is_success() {
            Ok(())
        } else {
            Err(format!("Health check returned {}", response.status()))
        }
    }

    /// Get authentication status
    pub async fn get_auth_status(&self) -> Result<AuthStatus, String> {
        let url = format!("{}/api/auth-status", self.base_url);

        let response = self
            .http_client
            .get(&url)
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .map_err(|e| format!("Request failed: {}", e))?;

        response
            .json()
            .await
            .map_err(|e| format!("Failed to parse response: {}", e))
    }

    /// Login to TastyTrade
    pub async fn login(
        &self,
        client_secret: &str,
        refresh_token: &str,
        remember_me: bool,
    ) -> Result<LoginResponse, String> {
        let url = format!("{}/api/login", self.base_url);

        let response = self
            .http_client
            .post(&url)
            .json(&serde_json::json!({
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "remember_me": remember_me,
            }))
            .timeout(Duration::from_secs(30))
            .send()
            .await
            .map_err(|e| format!("Request failed: {}", e))?;

        response
            .json()
            .await
            .map_err(|e| format!("Failed to parse response: {}", e))
    }

    /// Logout from TastyTrade
    pub async fn logout(&self, clear_credentials: bool) -> Result<LogoutResponse, String> {
        let url = format!("{}/api/logout", self.base_url);

        let response = self
            .http_client
            .post(&url)
            .json(&serde_json::json!({
                "clear_credentials": clear_credentials,
            }))
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .map_err(|e| format!("Request failed: {}", e))?;

        response
            .json()
            .await
            .map_err(|e| format!("Failed to parse response: {}", e))
    }

    pub fn stop(&self) -> Result<(), String> {
        let mut child_guard = self.child.lock().map_err(|e| e.to_string())?;

        if let Some(mut child) = child_guard.take() {
            log::info!("Stopping Python MCP server");
            let _ = child.kill();
            let _ = child.wait();
        }

        Ok(())
    }

    pub fn is_running(&self) -> bool {
        self.child.lock().map(|g| g.is_some()).unwrap_or(false)
    }

    pub fn get_base_url(&self) -> &str {
        &self.base_url
    }
}

impl Drop for SidecarManager {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}
