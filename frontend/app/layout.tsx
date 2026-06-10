import type { Metadata } from "next";
import { Geist_Mono, Inter, Inter_Tight, Geist } from "next/font/google";
import localFont from "next/font/local";
import { AuthProvider } from "@/lib/auth";
import { Toaster } from "sonner";
import "./globals.css";
import { cn } from "@/lib/utils";

const geist = Geist({subsets:['latin'],variable:'--font-sans'});

const googleSans = localFont({
  src: "../public/Google_Sans/GoogleSans-VariableFont_GRAD,opsz,wght.woff2",
  variable: "--font-display",
  display: "swap",
});

const inter = Inter({
  variable: "--font-body",
  subsets: ["latin"],
});

const interTight = Inter_Tight({
  variable: "--font-ui",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Lumen — AI Literature Review",
  description: "Illuminate your research with AI-powered literature analysis.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={cn("h-full", "antialiased", googleSans.variable, inter.variable, interTight.variable, geistMono.variable, "font-sans", geist.variable)}
    >
      <body className="min-h-full flex flex-col">
        <AuthProvider>
          {children}
          <Toaster position="top-right" toastOptions={{ style: { fontFamily: "var(--font-body)" } }} />
        </AuthProvider>
      </body>
    </html>
  );
}
