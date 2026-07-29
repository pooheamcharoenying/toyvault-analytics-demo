import "./globals.css";
import AuthGate from "@/components/AuthGate";
import DataStatusBar from "@/components/DataStatusBar";
import DataFreshnessBanner from "@/components/DataFreshnessBanner";
import Navbar from "@/components/Navbar";
import AssistantWidget from "@/components/AssistantWidget";
import AssistantProvider from "@/components/AssistantProvider";

export const metadata = {
  title: "ToyVault Work App",
  description: "ToyVault Business Analytics Dashboard",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <AuthGate>
          <AssistantProvider>
            <Navbar />
            <DataFreshnessBanner />
            <DataStatusBar />
            {children}
            <AssistantWidget />
          </AssistantProvider>
        </AuthGate>
      </body>
    </html>
  );
}

