const TOKEN_KEY = "face_auth_token";
const ROLE_KEY = "face_auth_role";
const USER_KEY = "face_auth_username";

export function getStoredAuth() {
  return {
    token: sessionStorage.getItem(TOKEN_KEY),
    role: sessionStorage.getItem(ROLE_KEY),
    username: sessionStorage.getItem(USER_KEY)
  };
}

export function setStoredAuth({ token, role, username }) {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(ROLE_KEY, role);
  if (username) sessionStorage.setItem(USER_KEY, username);
}

export function clearStoredAuth() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(ROLE_KEY);
  sessionStorage.removeItem(USER_KEY);
}
