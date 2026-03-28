import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";
import { useTheme } from "../hooks/useTheme";

export default function Layout() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-surface-alt)]">
      <header className="bg-[var(--color-surface)] border-b border-[var(--color-border)] px-4 md:px-8 py-3 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <span className="text-lg font-bold text-[var(--color-primary)]">upravpdf.eu</span>
          <nav className="hidden md:flex gap-1">
            {[
              { to: "/", label: "Nahrát PDF", exact: true },
              { to: "/history", label: "Historie" },
            ].map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.exact}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm font-medium ${
                    isActive
                      ? "bg-[var(--color-primary-light)] text-[var(--color-primary)]"
                      : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-[var(--color-text-secondary)] hidden md:block">{user?.email}</span>
          <button onClick={toggle} className="p-2 rounded-lg hover:bg-[var(--color-surface-alt)]">
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
          <button
            onClick={async () => { await logout(); navigate("/login"); }}
            className="text-sm text-[var(--color-text-secondary)] hover:text-red-600 px-2 py-1"
          >
            Odhlásit
          </button>
        </div>
      </header>
      <main className="flex-1 p-4 md:p-8 max-w-4xl w-full mx-auto">
        <Outlet />
      </main>
    </div>
  );
}
