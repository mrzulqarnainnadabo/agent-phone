const SESSION_KEY = "agent-phone.session";

export function getSessionToken(): string {
  if (typeof window === "undefined") return "";
  return window.sessionStorage.getItem(SESSION_KEY) || "";
}

export function setSessionToken(token: string): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(SESSION_KEY, token);
}

export function clearSessionToken(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(SESSION_KEY);
}

export function expireSession(): void {
  clearSessionToken();
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("agent-phone-session-expired"));
  }
}
