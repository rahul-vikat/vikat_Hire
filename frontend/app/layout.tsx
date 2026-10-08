import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "VikatHire Screening",
  description: "Evidence-driven candidate screening results.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
