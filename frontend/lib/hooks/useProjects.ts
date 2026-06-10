import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import type { ProjectListResponse, ProjectResponse } from "@/lib/types";

export function useProjects() {
  const { token } = useAuth();
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    apiFetch<ProjectListResponse>("/projects", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((data) => {
        setProjects(data.projects || []);
      })
      .catch(() => toast.error("Failed to load projects"))
      .finally(() => setLoading(false));
  }, [token]);

  return { projects, loading };
}
