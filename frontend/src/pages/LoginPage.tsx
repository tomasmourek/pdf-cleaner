import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import toast from "react-hot-toast";
import { authApi } from "../services/api";
import { useAuthStore } from "../stores/authStore";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const setUser = useAuthStore((s) => s.setUser);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const data = await authApi.login({ email, password, remember_me: false });
      if (!data.user?.has_pdf_access) {
        toast.error("PDF analýza vyžaduje plán PRO nebo BUSINESS.");
        return;
      }
      setUser(data.user);
      navigate("/");
    } catch (err: any) {
      toast.error(err.response?.data?.detail ?? "Přihlášení selhalo.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-surface-alt)] px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-[var(--color-primary)]">upravpdf.eu</h1>
          <p className="text-sm text-[var(--color-text-secondary)] mt-1">OCR analýza PDF a fotek pro autoservisy</p>
        </div>
        <div className="bg-[var(--color-surface)] rounded-xl shadow-[var(--shadow-card)] p-6">
          <h2 className="text-lg font-semibold mb-5">Přihlásit se</h2>
          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            <div>
              <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">E-mail</label>
              <input type="email" required className="input w-full" value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">Heslo</label>
              <input type="password" required className="input w-full" value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            <button type="submit" disabled={loading} className="btn btn-primary w-full">
              {loading ? "Přihlašuji…" : "Přihlásit se"}
            </button>
          </form>
          <p className="text-sm text-center text-[var(--color-text-secondary)] mt-4">
            Nemáte účet?{" "}
            <a href="https://upravcsv.eu/register" className="text-[var(--color-primary)] hover:underline font-medium">
              Registrovat se na upravcsv.eu
            </a>
          </p>
          <p className="text-xs text-center text-amber-600 mt-3 bg-amber-50 rounded-lg px-3 py-2">
            🔒 PDF analýza vyžaduje plán PRO nebo BUSINESS
          </p>
        </div>
      </div>
    </div>
  );
}
