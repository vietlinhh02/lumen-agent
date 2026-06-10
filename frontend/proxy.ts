import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_EXTENSIONS = /\.(png|jpg|jpeg|svg|webp|gif|ico|woff2?|ttf|otf|css|js|map|json|txt|xml)$/i;

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
  const { pathname } = request.nextUrl;

  // Allow public access to landing page
  if (pathname === "/") {
    return NextResponse.next();
  }

  // Allow public static files (images, fonts, css, js, etc.)
  if (PUBLIC_EXTENSIONS.test(pathname)) {
    return NextResponse.next();
  }

  const cookie = request.cookies.get("lumen_token");

  if (!cookie?.value || isJwtExpired(cookie.value)) {
    const response = NextResponse.redirect(new URL("/login", request.url));
    response.cookies.set("lumen_token", "", { path: "/", maxAge: 0 });
    return response;
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!login|register|api|_next|favicon.ico).*)"],
};
