import { AppNav } from "@/components/AppNav";
import { ChromeProvider } from "@/components/ChromeProvider";
import type { Metadata } from "next";
import { IBM_Plex_Mono, Newsreader } from "next/font/google";
import "./globals.css";

const serif = Newsreader({
  subsets: ["latin"],
  variable: "--font-display",
  style: ["normal", "italic"],
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Classifier ledger",
  description: "Inspect every Gmail classification, its trace, and its cost.",
};

const themeBoot = `(function(){try{var t=localStorage.getItem("classifier-theme");if(t==="light"||t==="dark"||t==="system")document.documentElement.dataset.theme=t;}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBoot }} />
      </head>
      <body className={`${serif.variable} ${mono.variable} grain min-h-screen`}>
        <ChromeProvider>
          <AppNav />
          {children}
        </ChromeProvider>
      </body>
    </html>
  );
}
