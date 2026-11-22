import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { ToastProvider } from "@/components/ui/Toast";
import { LanguageProvider } from "@/lib/language";

export const metadata: Metadata = {
  title: "BhoomiTrust AI — Land Record Digitization & Validation",
  description:
    "AI-powered land record digitization and validation system. Extract, validate, score, verify, trust.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans bg-paper text-ink antialiased">
        <LanguageProvider>
          <ToastProvider>
            <AuthProvider>{children}</AuthProvider>
          </ToastProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
