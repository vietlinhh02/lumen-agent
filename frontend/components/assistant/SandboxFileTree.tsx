"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { readSandboxFile } from "@/lib/api/assistant";
import { useAssistantStore } from "@/lib/stores/assistantStore";
import type { WorkspaceEntryFE } from "@/lib/types";
import {
  CaretDown,
  CaretRight,
  FileText,
  Folder,
  FolderOpen,
  X,
} from "@phosphor-icons/react";

interface TreeNode {
  name: string;
  path: string;
  isDir: boolean;
  size: number | null;
  children: TreeNode[];
}

function buildTree(flat: WorkspaceEntryFE[]): TreeNode[] {
  const root: TreeNode = { name: "/", path: "", isDir: true, size: null, children: [] };
  for (const f of flat) {
    const parts = f.path.split("/").filter(Boolean);
    let cur = root;
    let acc = "";
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      acc = acc ? `${acc}/${part}` : part;
      const last = i === parts.length - 1;
      let next = cur.children.find((c) => c.name === part);
      if (!next) {
        next = {
          name: part,
          path: acc,
          isDir: last ? f.is_dir : true,
          size: last ? f.size_bytes : null,
          children: [],
        };
        cur.children.push(next);
      }
      cur = next;
    }
  }
  const sortRec = (n: TreeNode) => {
    n.children.sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    n.children.forEach(sortRec);
  };
  sortRec(root);
  return root.children;
}

function fmtBytes(n: number | null): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function FilePreview({ projectId, path, onClose }: { projectId: string; path: string; onClose: () => void }) {
  const { token } = useAuth();
  const [fetched, setFetched] = useState<{
    path: string;
    text: string | null;
    error: string | null;
  } | null>(null);
  useEffect(() => {
    let cancelled = false;
    if (!token) return;
    readSandboxFile(token, projectId, `/workspace/${path}`)
      .then((r) => {
        if (cancelled) return;
        setFetched({ path, text: r.content, error: null });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setFetched({
          path,
          text: null,
          error: e instanceof Error ? e.message : "Read failed",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, path, token]);
  const loading = !fetched || fetched.path !== path;
  return (
    <div className="mx-1 my-1 rounded-md border border-hairline bg-canvas">
      <div className="flex items-center justify-between border-b border-hairline px-2 py-1">
        <span className="font-mono text-[10px] text-charcoal">{path}</span>
        <button
          onClick={onClose}
          className="rounded p-0.5 text-ash hover:bg-surface-bone hover:text-ink"
          title="Close"
        >
          <X size={10} weight="bold" />
        </button>
      </div>
      <pre className="max-h-56 overflow-auto p-2 font-mono text-[10.5px] text-ink/80 whitespace-pre-wrap break-words">
        {loading ? (
          <span className="text-charcoal/50">Loading…</span>
        ) : fetched?.error ? (
          <span className="text-red-700">{fetched.error}</span>
        ) : (
          fetched?.text ?? ""
        )}
      </pre>
    </div>
  );
}

function NodeView({
  node,
  depth,
  projectId,
  onSelect,
  selectedPath,
}: {
  node: TreeNode;
  depth: number;
  projectId: string;
  onSelect: (path: string) => void;
  selectedPath: string | null;
}) {
  const [open, setOpen] = useState(depth < 1);
  const isFile = !node.isDir;
  const previewing = isFile && selectedPath === node.path;
  return (
    <div>
      <button
        type="button"
        onClick={() => {
          if (isFile) {
            onSelect(node.path);
          } else {
            setOpen((o) => !o);
          }
        }}
        className="flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left font-mono text-[11px] text-ink hover:bg-surface-bone/70"
        style={{ paddingLeft: 4 + depth * 12 }}
      >
        {node.isDir ? (
          open ? (
            <CaretDown size={10} weight="bold" className="text-ash" />
          ) : (
            <CaretRight size={10} weight="bold" className="text-ash" />
          )
        ) : (
          <span className="w-2.5" />
        )}
        {node.isDir ? (
          open ? (
            <FolderOpen size={12} weight="duotone" className="text-amber-600" />
          ) : (
            <Folder size={12} weight="duotone" className="text-amber-600" />
          )
        ) : (
          <FileText size={12} weight="duotone" className="text-charcoal" />
        )}
        <span className="truncate">{node.name}</span>
        <span className="ml-auto text-[10px] text-ash">{fmtBytes(node.size)}</span>
      </button>
      {node.isDir && open && (
        <div>
          {node.children.map((c) => (
            <NodeView
              key={c.path}
              node={c}
              depth={depth + 1}
              projectId={projectId}
              onSelect={onSelect}
              selectedPath={selectedPath}
            />
          ))}
        </div>
      )}
      {previewing && (
        <div style={{ marginLeft: 4 + depth * 12 + 4 }}>
          <FilePreview
            projectId={projectId}
            path={node.path}
            onClose={() => onSelect(node.path)}
          />
        </div>
      )}
    </div>
  );
}

export function SandboxFileTree({ files }: { files: WorkspaceEntryFE[] }) {
  const projectId = useAssistantStore((s) => s.state.projectId);
  const tree = buildTree(files);
  const [openPath, setOpenPath] = useState<string | null>(null);

  if (files.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-hairline px-3 py-4 text-center text-[11px] text-charcoal/60">
        Workspace is empty. The agent will drop files here as it works.
      </div>
    );
  }
  return (
    <div className="space-y-0.5">
      {tree.map((n) => (
        <NodeView
          key={n.path}
          node={n}
          depth={0}
          projectId={projectId ?? ""}
          onSelect={(p) => setOpenPath((cur) => (cur === p ? null : p))}
          selectedPath={openPath}
        />
      ))}
    </div>
  );
}
