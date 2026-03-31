import "@/app/globals.css";
import { Navbar } from "@/components/Navbar";
import { Providers } from "@/providers/Providers";

export const metadata = {
  title: "Tender AI Frontend",
  description: "Frontend for AI analysis of tender documentation",
};

interface RootLayoutProps {
  children: React.ReactNode;
}

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <Navbar />
          <main>
            <div className="container">{children}</div>
          </main>
        </Providers>
      </body>
    </html>
  );
}