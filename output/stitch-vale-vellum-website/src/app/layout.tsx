import './globals.css';

export const metadata = { title: "Vale & Vellum", description: 'AI-assisted everyday workflow tool' };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
