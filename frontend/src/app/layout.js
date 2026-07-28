import "./globals.css";
import AuthGate from "@/components/AuthGate";
import DataStatusBar from "@/components/DataStatusBar";
import DataFreshnessBanner from "@/components/DataFreshnessBanner";
import Navbar from "@/components/Navbar";

export const metadata = {
  title: "ToyVault Work App",
  description: "ToyVault Business Analytics Dashboard",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <AuthGate>
          <Navbar />
          <DataFreshnessBanner />
          <DataStatusBar />
          {children}
        </AuthGate>
      </body>
    </html>
  );
}

