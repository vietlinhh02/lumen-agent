"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Lock, Sun, Moon, CheckCircle, XCircle } from "@phosphor-icons/react";
import { useUIStore } from "@/lib/stores/ui-store";
import { useSettingsStore } from "@/lib/stores/settings-store";
import { formatDate } from "@/lib/utils";
import type { UserProfile } from "@/lib/types";

export function ProfileSection({ profile }: { profile: UserProfile }) {
  const theme = useUIStore((s) => s.theme);
  const toggleTheme = useUIStore((s) => s.toggleTheme);
  const changePassword = useSettingsStore((s) => s.changePassword);
  const updateProfileName = useSettingsStore((s) => s.updateProfileName);
  const [displayName, setDisplayName] = useState(profile.display_name ?? "");
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [saving, setSaving] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);

  async function handleUpdateProfile(e: React.FormEvent) {
    e.preventDefault();
    const name = displayName.trim().replace(/\s+/g, " ");
    if (!name) {
      toast.error("Display name is required");
      return;
    }
    if (name.length > 80) {
      toast.error("Display name must be 80 characters or fewer");
      return;
    }
    if (name === (profile.display_name ?? "")) {
      toast.message("No profile changes to save");
      return;
    }

    setSavingProfile(true);
    const updated = await updateProfileName(name);
    setSavingProfile(false);
    if (updated) {
      toast.success("Name updated");
      setDisplayName(updated.display_name ?? "");
    } else {
      toast.error("Failed to update name");
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    if (newPw !== confirmPw) { toast.error("Passwords do not match"); return; }
    if (newPw.length < 6) { toast.error("Password must be at least 6 characters"); return; }
    setSaving(true);
    const ok = await changePassword(currentPw, newPw);
    setSaving(false);
    if (ok) {
      toast.success("Password updated");
      setCurrentPw(""); setNewPw(""); setConfirmPw("");
    } else {
      toast.error("Failed to update password");
    }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-[12px] bg-surface-card p-6" style={{ border: "1px solid var(--hairline)" }}>
        <h2 className="font-ui text-base font-semibold text-ink mb-4">Account Information</h2>
        <form onSubmit={handleUpdateProfile} className="mb-5 grid gap-3 sm:max-w-md">
          <div>
            <label className="font-ui block text-[12px] font-semibold text-charcoal mb-1.5">
              Display Name
            </label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="focus-ring h-[44px] w-full rounded-full bg-surface-bone px-4 font-ui text-sm text-ink outline-none"
              style={{ border: "1px solid var(--hairline)" }}
              maxLength={80}
              required
            />
          </div>
          <button
            type="submit"
            disabled={savingProfile}
            className="focus-ring font-ui h-[42px] w-full rounded-full bg-primary px-5 text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50 sm:w-fit"
          >
            {savingProfile ? "Saving…" : "Update Name"}
          </button>
        </form>

        <div className="space-y-3 border-t border-hairline pt-5">
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
  const users = useSettingsStore((s) => s.users);
  const loading = useSettingsStore((s) => s.loadingUsers);
  const fetchUsers = useSettingsStore((s) => s.fetchUsers);
  const toggleUserActive = useSettingsStore((s) => s.toggleUserActive);

  useEffect(() => {
    if (users.length === 0) void fetchUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function toggleActive(userId: string, currentActive: boolean) {
    const updated = await toggleUserActive(userId, currentActive);
    if (updated) {
      toast.success(`User ${updated.is_active ? "activated" : "deactivated"}`);
    } else {
      toast.error("Update failed");
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
                <th className="font-ui text-[11px] font-semibold text-ash uppercase tracking-wide text-left px-6 py-3">Name</th>
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
                  <td className="px-6 py-3 font-ui text-sm text-charcoal">
                    {u.display_name || "—"}
                  </td>
                  <td className="px-6 py-3 font-ui text-sm text-charcoal capitalize">{u.role}</td>
                  <td className="px-6 py-3">
                    <span className={`font-ui inline-flex items-center gap-1 text-[12px] font-semibold ${u.is_active ? "text-green-700" : "text-red-700"}`}>
                      {u.is_active ? <CheckCircle size={12} /> : <XCircle size={12} />}
                      {u.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-6 py-3 font-ui text-sm text-charcoal">{formatDate(u.created_at)}</td>
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
