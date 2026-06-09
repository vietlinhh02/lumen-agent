import { NextResponse, type NextRequest } from "next/server";

function isJwtExpired(token: string): boolean {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return true;
    const payload = JSON.parse(
      Buffer.from(parts[1], "base64url").toString("utf-8")
    );
    return payload.exp ? Date.now() >= payload.exp * 1000 : true;
  } catch {
    return true;
  }
}

export default function proxy(request: NextRequest) {
  const cookie = request.cookies.get("lumen_token");

  if (!cookie?.value || isJwtExpired(cookie.value)) {
    const response = NextResponse.redirect(new URL("/login", request.url));
    response.cookies.set("lumen_token", "", { path: "/", maxAge: 0 });
    return response;
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!login|register|api|_next|favicon.ico|.*\\.svg).*)"],
};
