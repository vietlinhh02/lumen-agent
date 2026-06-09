interface JwtPayload {
  sub?: string;
  email?: string;
  exp?: number;
  iat?: number;
}

function base64UrlDecode(input: string): string {
  const base64 = input.replace(/-/g, "+").replace(/_/g, "/");
  const decoded = atob(base64);
  let result = "";
  for (let i = 0; i < decoded.length; i++) {
    result += "%" + ("00" + decoded.charCodeAt(i).toString(16)).slice(-2);
  }
  return decodeURIComponent(result);
}

export function decodeTokenPayload(token: string): JwtPayload | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    return JSON.parse(base64UrlDecode(parts[1]));
  } catch {
    return null;
  }
}

export function isTokenExpired(token: string): boolean {
  const payload = decodeTokenPayload(token);
  if (!payload?.exp) return true;
  return Date.now() >= payload.exp * 1000;
}

export const TOKEN_KEY = "lumen_token";
