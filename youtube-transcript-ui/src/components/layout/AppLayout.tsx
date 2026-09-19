import { useState } from "react";
import { Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Sidebar } from "./Sidebar";
import { MobileHeader } from "./MobileHeader";
import { ArtifactProvider, useArtifacts } from "@/contexts/ArtifactContext";
import { ArtifactPanel } from "@/components/artifacts/ArtifactPanel";

function LayoutShell() {
  const { isOpen } = useArtifacts();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-background">
      <MobileHeader onOpenSidebar={() => setIsSidebarOpen(true)} />
      <Sidebar isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />
      <main
        className={cn(
          "pt-14 lg:pl-64 lg:pt-0 transition-[padding] duration-300",
          // Make room for the docked artifact panel on large screens; on small
          // screens the panel overlays the content instead of pushing it.
          isOpen && "lg:pr-[40rem]"
        )}
      >
        <div className="min-h-screen">
          <Outlet />
        </div>
      </main>
      <ArtifactPanel />
    </div>
  );
}

export function AppLayout() {
  return (
    <ArtifactProvider>
      <LayoutShell />
    </ArtifactProvider>
  );
}
