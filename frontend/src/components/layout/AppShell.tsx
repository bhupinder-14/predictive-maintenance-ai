import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Activity, ArrowUpRight, ChevronLeft, ChevronRight, CircuitBoard,
  ClipboardList, Command, Gauge, Menu, RadioTower, Settings2, ShieldCheck,
  X,
} from "lucide-react";
import { ConnectionIndicator } from "./ConnectionIndicator";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navigation = [
  { label: "Overview", to: "/", icon: Gauge, end: true },
  { label: "Equipment", to: "/equipment", icon: CircuitBoard },
  { label: "Prediction Lab", to: "/prediction-lab", icon: Activity },
  { label: "Prediction History", to: "/prediction-history", icon: ClipboardList },
  { label: "Drift Monitoring", to: "/drift", icon: RadioTower },
  { label: "System Health", to: "/system", icon: ShieldCheck },
];

const titles: Record<string, string> = {
  "/": "Overview",
  "/equipment": "Equipment",
  "/prediction-lab": "Prediction Lab",
  "/prediction-history": "Prediction History",
  "/drift": "Drift Monitoring",
  "/system": "System Health",
};

function SidebarContent({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  return (
    <>
      <Link className={cn("brand", collapsed && "brand-collapsed")} to="/" onClick={onNavigate} aria-label="ForgeSight home">
        <span className="brand-mark"><Command size={20} strokeWidth={2.2} /></span>
        {!collapsed && <span className="brand-copy"><strong>ForgeSight</strong><small>INDUSTRIAL INTELLIGENCE</small></span>}
      </Link>
      <div className="nav-section-label">WORKSPACE</div>
      <nav aria-label="Primary navigation" className="primary-nav">
        {navigation.map(({ label, to, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            title={collapsed ? label : undefined}
            aria-label={collapsed ? label : undefined}
            className={({ isActive }) => cn("nav-link", isActive && "nav-link-active", collapsed && "nav-link-collapsed")}
          >
            <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
            {!collapsed && <span>{label}</span>}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-build"><span className="build-indicator" /><span>Command center</span><span className="build-version">M6</span></div>
        <div className="sidebar-footer"><Settings2 size={15} /><span>Operations workspace</span></div>
      </div>
    </>
  );
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const menuTriggerRef = useRef<HTMLButtonElement>(null);
  const mobileDialogRef = useRef<HTMLDialogElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const wasMobileOpen = useRef(false);
  const location = useLocation();
  const title = titles[location.pathname] ?? "Operations";

  useEffect(() => {
    const dialog = mobileDialogRef.current;
    if (!dialog) return;
    if (mobileOpen) {
      if (!dialog.open) dialog.showModal();
      wasMobileOpen.current = true;
      closeButtonRef.current?.focus();
      const keepFocusInside = (event: FocusEvent) => {
        if (event.target instanceof Node && !dialog.contains(event.target)) closeButtonRef.current?.focus();
      };
      document.addEventListener("focusin", keepFocusInside);
      return () => document.removeEventListener("focusin", keepFocusInside);
    }
    if (dialog.open) dialog.close();
    if (wasMobileOpen.current) {
      menuTriggerRef.current?.focus();
      wasMobileOpen.current = false;
    }
  }, [mobileOpen]);

  return (
    <div className="app-frame">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <aside className={cn("sidebar", collapsed && "sidebar-collapsed")}>
        <SidebarContent collapsed={collapsed} />
        <button
          className="sidebar-collapse"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          onClick={() => setCollapsed((value) => !value)}
        >
          {collapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
        </button>
      </aside>

      <dialog
        id="mobile-navigation"
        ref={mobileDialogRef}
        className="mobile-sidebar"
        aria-label="Mobile navigation"
        aria-modal={mobileOpen ? "true" : undefined}
        onCancel={(event) => { event.preventDefault(); setMobileOpen(false); }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            setMobileOpen(false);
            return;
          }
          if (event.key !== "Tab") return;
          const dialog = mobileDialogRef.current;
          if (!dialog) return;
          const focusable = Array.from(dialog.querySelectorAll<HTMLElement>('a[href], button:not(:disabled), [tabindex]:not([tabindex="-1"])'));
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (!first || !last) {
            event.preventDefault();
          } else if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }}
      >
        <div className="mobile-sidebar-head">
          <SidebarContent collapsed={false} onNavigate={() => setMobileOpen(false)} />
          <button ref={closeButtonRef} type="button" className="button button-ghost button-icon" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><X size={18} /></button>
        </div>
      </dialog>

      <div className="main-column">
        <header className="topbar">
          <div className="topbar-left">
            <Button ref={menuTriggerRef} className="mobile-menu-button" variant="ghost" size="icon" aria-label="Open navigation" aria-expanded={mobileOpen} aria-controls="mobile-navigation" onClick={() => setMobileOpen(true)}><Menu size={19} /></Button>
            <div className="breadcrumbs"><span>Operations</span><span className="breadcrumb-divider">/</span><strong>{title}</strong></div>
          </div>
          <div className="topbar-right">
            <span className="topbar-environment">BACKEND STATUS</span>
            <ConnectionIndicator />
          </div>
        </header>
        <main id="main-content" className="page-canvas">
          <Outlet />
          <footer className="page-footer">
            <span>FORGESIGHT <span className="footer-separator">/</span> INDUSTRIAL AI OPERATIONS</span>
            <Link to="/system" className="footer-link">Service status <ArrowUpRight size={12} /></Link>
          </footer>
        </main>
      </div>
    </div>
  );
}
