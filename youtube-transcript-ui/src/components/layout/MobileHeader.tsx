import { Menu, Youtube } from "lucide-react";
import { Button } from "@/components/ui/button";

interface MobileHeaderProps {
  onOpenSidebar: () => void;
}

export function MobileHeader({ onOpenSidebar }: MobileHeaderProps) {
  return (
    <header className="fixed left-0 right-0 top-0 z-30 flex h-14 items-center gap-3 border-b border-sidebar-border bg-sidebar px-4 lg:hidden">
      <Button
        variant="ghost"
        size="icon"
        className="h-9 w-9 flex-shrink-0"
        onClick={onOpenSidebar}
        aria-label="Open navigation menu"
      >
        <Menu className="h-5 w-5" />
      </Button>
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
        <Youtube className="h-4 w-4 text-primary-foreground" />
      </div>
      <span className="text-sm font-semibold text-foreground">Transcript API</span>
    </header>
  );
}
