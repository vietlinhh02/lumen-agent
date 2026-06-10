"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { User, Shield } from "@phosphor-icons/react";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { ProfileSection, AdminSection } from "@/components/settings";
import type { UserProfile } from "@/lib/types";

export default function SettingsPage() {
  const { token } = useAuth();
  const [activeTab, setActiveTab] = useState<"profile" | "admin">("profile");
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    if (!token) return;
    apiFetch<UserProfile>("/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((u) => { setProfile(u); setIsAdmin(u.role === "admin"); })
      .catch(() => toast.error("Failed to load profile"));
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
          </div>

          {activeTab === "profile" && profile && <ProfileSection profile={profile} />}
          {activeTab === "admin" && isAdmin && <AdminSection />}
        </div>
      </div>
    </div>
  );
}
