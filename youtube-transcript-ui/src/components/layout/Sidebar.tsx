import { NavLink, useLocation } from "react-router-dom";
import { Home, FileText, MessageSquare, MessagesSquare, Settings, Youtube, Mail, Shield, FolderOpen, ListVideo, History } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { UserMenu } from "@/components/auth/UserMenu";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { Separator } from "@/components/ui/separator";

const mainNavItems = [
  { path: "/", icon: Home, label: "Home" },
  { path: "/transcripts", icon: FileText, label: "Transcripts" },
  { path: "/playlists", icon: ListVideo, label: "Playlists" },
  { path: "/watch-history", icon: History, label: "Watch History" },
  { path: "/sessions", icon: MessageSquare, label: "Sessions" },
  { path: "/cross-chat", icon: MessagesSquare, label: "Cross-Chat" },
  { path: "/documents", icon: FolderOpen, label: "Documents" },
  { path: "/settings", icon: Settings, label: "Settings" },
];

const userNavItems = [
  { path: "/invitations", icon: Mail, label: "Invitations" },
];

const adminNavItems = [
  { path: "/admin/users", icon: Shield, label: "User Management" },
];

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const location = useLocation();
  const { isAdmin } = useAuth();

  const renderNavItem = (item: { path: string; icon: React.ComponentType<{ className?: string }>; label: string }) => {
    const isActive =
      item.path === "/"
        ? location.pathname === "/"
        : location.pathname.startsWith(item.path);

    return (
      <NavLink
        key={item.path}
        to={item.path}
        onClick={onClose}
        className={cn(
          "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
          isActive
            ? "bg-sidebar-accent text-sidebar-accent-foreground"
            : "text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground"
        )}
      >
        <item.icon className="h-5 w-5" />
        {item.label}
      </NavLink>
    );
  };

  return (
    <>
      {/* Mobile backdrop — clicking it closes the drawer. */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <aside
        className={cn(
          "fixed left-0 top-0 z-50 h-screen w-72 max-w-[85vw] border-r border-sidebar-border bg-sidebar transition-transform duration-300 lg:z-40 lg:w-64 lg:max-w-none lg:translate-x-0",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-full flex-col">
          {/* Logo */}
          <div className="flex h-16 items-center gap-3 border-b border-sidebar-border px-6">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary">
              <Youtube className="h-5 w-5 text-primary-foreground" />
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-semibold text-foreground">Transcript API</span>
              <span className="text-xs text-muted-foreground">YouTube Extractor</span>
            </div>
          </div>

          {/* Navigation */}
          <nav className="flex-1 space-y-1 px-3 py-4 overflow-y-auto">
            {/* Main Navigation */}
            {mainNavItems.map(renderNavItem)}

            {/* User Navigation */}
            <Separator className="my-4" />
            <div className="px-3 py-1">
              <span className="text-xs font-medium text-muted-foreground">Account</span>
            </div>
            {userNavItems.map(renderNavItem)}

            {/* Admin Navigation */}
            {isAdmin && (
              <>
                <Separator className="my-4" />
                <div className="px-3 py-1">
                  <span className="text-xs font-medium text-muted-foreground">Admin</span>
                </div>
                {adminNavItems.map(renderNavItem)}
              </>
            )}
          </nav>

          {/* User Menu */}
          <div className="border-t border-sidebar-border p-3 space-y-1">
            <ThemeToggle />
            <UserMenu />
          </div>
        </div>
      </aside>
    </>
  );
}
