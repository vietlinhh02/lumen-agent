"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { User, Lock, Sun, Moon, CheckCircle, XCircle } from "@phosphor-icons/react";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import type { UserProfile, AdminUser } from "@/lib/types";

export function ProfileSection({ profile }: { profile: UserProfile }) {
  const { token } = useAuth();
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [saving, setSaving] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const stored = localStorage.getItem("theme") as "light" | "dark" | null;
    if (stored) setTheme(stored);
  }, []);

  function toggleTheme() {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    localStorage.setItem("theme", next);
    document.documentElement.classList.toggle("dark", next === "dark");
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    if (newPw !== confirmPw) { toast.error("Passwords do not match"); return; }
    if (newPw.length < 6) { toast.error("Password must be at least 6 characters"); return; }
    setSaving(true);
    try {
      await apiFetch("/auth/password", {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: currentPw, new_password: newPw }),
      });
      toast.success("Password updated");
      setCurrentPw(""); setNewPw(""); setConfirmPw("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update password");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-[12px] bg-surface-card p-6" style={{ border: "1px solid var(--hairline)" }}>
        <h2 className="font-ui text-base font-semibold text-ink mb-4">Account Information</h2>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="font-ui text-sm text-charcoal">Email</span>
            <span className="font-ui text-sm font-medium text-ink">{profile.email}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="font-ui text-sm text-charcoal">Role</span>
            <span className="font-ui text-sm font-medium text-ink capitalize">{profile.role}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="font-ui text-sm text-charcoal">Status</span>
            <span className={`font-ui inline-flex items-center gap-1 text-sm font-medium ${profile.is_active ? "text-green-700" : "text-red-700"}`}>
              {profile.is_active ? <CheckCircle size={14} /> : <XCircle size={14} />}
              {profile.is_active ? "Active" : "Inactive"}
            </span>
          </div>
        </div>
      </div>

      <div className="rounded-[12px] bg-surface-card p-6" style={{ border: "1px solid var(--hairline)" }}>
        <h2 className="font-ui text-base font-semibold text-ink mb-4">Appearance</h2>
        <button onClick={toggleTheme} className="flex items-center justify-between w-full">
          <div className="flex items-center gap-3">
            {theme === "light" ? <Sun size={20} className="text-amber-500" /> : <Moon size={20} className="text-indigo-400" />}
            <div className="text-left">
              <p className="font-ui text-sm font-medium text-ink">{theme === "light" ? "Light Mode" : "Dark Mode"}</p>
              <p className="font-ui text-[12px] text-charcoal">Toggle between light and dark theme</p>
            </div>
          </div>
          <div className={`relative h-[28px] w-[48px] rounded-full transition-colors ${theme === "dark" ? "bg-primary" : "bg-stone/30"}`}>
            <div className={`absolute top-[3px] h-[22px] w-[22px] rounded-full bg-white shadow transition-transform ${theme === "dark" ? "translate-x-[23px]" : "translate-x-[3px]"}`} />
          </div>
        </button>
      </div>

      <div className="rounded-[12px] bg-surface-card p-6" style={{ border: "1px solid var(--hairline)" }}>
        <h2 className="font-ui text-base font-semibold text-ink mb-4 flex items-center gap-2"><Lock size={18} />Change Password</h2>
        <form onSubmit={handleChangePassword} className="space-y-4 max-w-sm">
          <div>
            <label className="font-ui block text-[12px] font-semibold text-charcoal mb-1.5">Current Password</label>
            <input type="password" value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} className="focus-ring h-[44px] w-full rounded-full bg-surface-bone px-4 font-ui text-sm text-ink outline-none" style={{ border: "1px solid var(--hairline)" }} required />
          </div>
          <div>
            <label className="font-ui block text-[12px] font-semibold text-charcoal mb-1.5">New Password</label>
            <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} className="focus-ring h-[44px] w-full rounded-full bg-surface-bone px-4 font-ui text-sm text-ink outline-none" style={{ border: "1px solid var(--hairline)" }} required minLength={6} />
          </div>
          <div>
            <label className="font-ui block text-[12px] font-semibold text-charcoal mb-1.5">Confirm New Password</label>
            <input type="password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} className="focus-ring h-[44px] w-full rounded-full bg-surface-bone px-4 font-ui text-sm text-ink outline-none" style={{ border: "1px solid var(--hairline)" }} required minLength={6} />
          </div>
          <button type="submit" disabled={saving} className="focus-ring font-ui h-[44px] rounded-full bg-primary px-5 text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50">
            {saving ? "Saving…" : "Update Password"}
          </button>
        </form>
      </div>
    </div>
  );
}

export function AdminSection() {
  const { token } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<{ items: AdminUser[]; total: number }>("/admin/users", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((data) => setUsers(data.items || []))
      .catch(() => toast.error("Failed to load users"))
      .finally(() => setLoading(false));
  }, [token]);

  async function toggleActive(userId: string, currentActive: boolean) {
    try {
      const updated = await apiFetch<AdminUser>(`/admin/users/${userId}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !currentActive }),
      });
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)));
      toast.success(`User ${updated.is_active ? "activated" : "deactivated"}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Update failed");
    }
  }

  return (
    <div className="rounded-[12px] bg-surface-card overflow-hidden" style={{ border: "1px solid var(--hairline)" }}>
      <div className="px-6 py-4" style={{ borderBottom: "1px solid var(--hairline)" }}>
        <h2 className="font-ui text-base font-semibold text-ink">User Management</h2>
        <p className="font-ui text-[12px] text-charcoal mt-1">{users.length} registered users</p>
      </div>
      {loading ? (
        <div className="p-6 space-y-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-12 rounded bg-surface-bone animate-pulse" />)}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-surface-bone/50">
                <th className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-6 py-3">Email</th>
                <th className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-6 py-3">Role</th>
                <th className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-6 py-3">Status</th>
                <th className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-6 py-3">Joined</th>
                <th className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-right px-6 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-surface-bone/30 transition-colors" style={{ borderTop: "1px solid var(--hairline)" }}>
                  <td className="px-6 py-3 font-ui text-sm text-ink">{u.email}</td>
                  <td className="px-6 py-3 font-ui text-sm text-charcoal capitalize">{u.role}</td>
                  <td className="px-6 py-3">
                    <span className={`font-ui inline-flex items-center gap-1 text-[12px] font-semibold ${u.is_active ? "text-green-700" : "text-red-700"}`}>
                      {u.is_active ? <CheckCircle size={12} /> : <XCircle size={12} />}
                      {u.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-6 py-3 font-ui text-sm text-charcoal">{new Date(u.created_at).toLocaleDateString()}</td>
                  <td className="px-6 py-3 text-right">
                    <button onClick={() => toggleActive(u.id, u.is_active)} className={`font-ui text-[12px] font-semibold px-3 py-1.5 rounded-full transition-colors ${u.is_active ? "bg-red-50 text-red-700 hover:bg-red-100" : "bg-green-50 text-green-700 hover:bg-green-100"}`}>
                      {u.is_active ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
