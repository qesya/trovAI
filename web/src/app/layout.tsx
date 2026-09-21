import type { Metadata } from "next";
import { DM_Sans, Fraunces } from "next/font/google";
import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";
import { SavedDrawer } from "@/components/SavedDrawer";
import { StoreProvider } from "@/components/store";
import "./globals.css";

const body = DM_Sans({ variable: "--font-body", subsets: ["latin"] });
const heading = Fraunces({ variable: "--font-heading", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "TrovAI · Assistente allo shopping", template: "%s · TrovAI" },
  description:
    "Trova prodotti usando il linguaggio naturale e confronta le opzioni prima di acquistare sul sito del negozio.",
  icons: { icon: "/trovai-icon.png" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="it" className={`${body.variable} ${heading.variable}`}>
      <body className="flex min-h-dvh flex-col font-sans antialiased">
        <StoreProvider>
          <Header />
          <main className="flex-1">{children}</main>
          <Footer />
          <SavedDrawer />
        </StoreProvider>
      </body>
    </html>
  );
}
