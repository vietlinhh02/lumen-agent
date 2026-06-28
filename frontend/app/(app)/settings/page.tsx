"use client";

import { useEffect } from "react";
import { toast } from "sonner";
import { User, Shield, ChartLineUp } from "@phosphor-icons/react";
import { useAuth } from "@/lib/stores/auth-store";
import { useSettingsStore } from "@/lib/stores/settings-store";
import { ProfileSection, AdminSection, UsageSection } from "@/components/settings";

export default function SettingsPage() {
  const token = useAuth((s) => s.token);
  const activeTab = useSettingsStore((s) => s.activeTab);
  const setActiveTab = useSettingsStore((s) => s.setActiveTab);
  const profile = useSettingsStore((s) => s.profile);
  const isAdmin = useSettingsStore((s) => s.isAdmin);
  const fetchProfile = useSettingsStore((s) => s.fetchProfile);

  useEffect(() => {
    if (!token) return;
    void fetchProfile().catch(() => toast.error("Failed to load profile"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <div className="min-h-screen bg-canvas">
      <div className="px-4 sm:px-6 py-6">
        <div className="flex flex-col gap-6">
          <div>
            <h1 className="font-display text-[32px] font-bold leading-[1.0] text-ink" style={{ letterSpacing: "-1px" }}>Settings</h1>
            <p className="mt-2 text-sm text-charcoal">Manage your account and application preferences.</p>
          </div>

          <div className="flex gap-1 rounded-[10px] bg-surface-bone p-1 w-fit">
            <button
              onClick={() => setActiveTab("profile")}
              className={`font-ui flex items-center gap-2 rounded-[8px] px-4 py-2 text-sm font-semibold transition-colors ${
                activeTab === "profile" ? "bg-surface-card text-ink shadow-sm" : "text-charcoal hover:text-ink"
              }`}
            >
              <User size={16} />Profile
            </button>
            {isAdmin && (
              <button
                onClick={() => setActiveTab("admin")}
                className={`font-ui flex items-center gap-2 rounded-[8px] px-4 py-2 text-sm font-semibold transition-colors ${
                  activeTab === "admin" ? "bg-surface-card text-ink shadow-sm" : "text-charcoal hover:text-ink"
                }`}
              >
                <Shield size={16} />Admin
              </button>
            )}
            {isAdmin && (
              <button
                onClick={() => setActiveTab("usage")}
                className={`font-ui flex items-center gap-2 rounded-[8px] px-4 py-2 text-sm font-semibold transition-colors ${
                  activeTab === "usage" ? "bg-surface-card text-ink shadow-sm" : "text-charcoal hover:text-ink"
                }`}
              >
                <ChartLineUp size={16} />Usage & Cost
              </button>
            )}
          </div>

          {activeTab === "profile" && profile && <ProfileSection profile={profile} />}
          {activeTab === "admin" && isAdmin && <AdminSection />}
          {activeTab === "usage" && isAdmin && <UsageSection />}
        </div>
      </div>
    </div>
  );
}
