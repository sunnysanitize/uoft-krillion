import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Pixelify_Sans } from "next/font/google";
import "./globals.css";

const pixel = Pixelify_Sans({ subsets: ["latin"], weight: ["400", "500", "700"], variable: "--font-pixelify" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex" });

export const metadata: Metadata = {
  title: "KrillionTO · Deeper dive into UofT",
  description: "KrillionTO: a daily UofT trivia dive. Deeper dive into UofT. Rarer answers sink deeper.",
};

export const viewport: Viewport = { themeColor: "#040a16" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${pixel.variable} ${mono.variable}`}>
      <body>
        {children}
        <div className="scanlines" aria-hidden />
      </body>
    </html>
  );
}
