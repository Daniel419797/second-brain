import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "Friday Command Center",
  description: "Friday v2 local dashboard"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
