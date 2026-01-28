export interface AuthStatusData {
  authenticated: boolean;
  has_stored_credentials: boolean;
}

export interface LoginResult {
  success: boolean;
  message?: string;
  error?: string;
}

export interface LogoutResult {
  success: boolean;
}
