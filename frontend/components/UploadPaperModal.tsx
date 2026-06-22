"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  X,
  UploadSimple,
  CircleNotch,
  Trash,
  CaretDown,
  CheckCircle,
  WarningCircle,
} from "@phosphor-icons/react";
import { apiFetch } from "@/lib/api";
import type {
  ConfirmUploadItem,
  UploadResponse,
  UploadStatusItem,
} from "@/lib/types";

const MAX_FILES = 5;
const MAX_BYTES = 30 * 1024 * 1024;
const ALLOWED_EXT = [".pdf", ".md"];

type Phase = "select" | "confirm";

// One row in the confirm form (editable metadata for a single uploaded file).
interface DraftRow {
  projectPaperId: string;
  filename: string;
  fullTextStatus: string | null;
  title: string;
  authors: string; // comma-separated names while editing
  year: string;
  venue: string;
  abstract: string;
}

const TERMINAL = new Set(["completed", "failed", "ocr_required"]);

const IPT =
  "w-full rounded-[9px] px-3 py-2 font-ui text-[13px] text-ink bg-surface-card outline-none focus-ring";
const IPT_STYLE = { border: "1px solid var(--hairline)" } as const;

function extOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

export function UploadPaperModal({
  projectId,
  token,
  onClose,
  onConfirmed,
}: {
  projectId: string;
  token: string;
  onClose: () => void;
  onConfirmed: () => void;
}) {
  const [phase, setPhase] = useState<Phase>("select");
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Confirm phase state.
  const [rows, setRows] = useState<DraftRow[]>([]);
  const [filenames, setFilenames] = useState<Record<string, string>>({});
  const [ingesting, setIngesting] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const overlayRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const authHeader = { Authorization: `Bearer ${token}` };

  // Escape closes only during file selection (confirm phase must discard first).
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && phase === "select" && !uploading) onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [phase, uploading, onClose]);

  // ── File selection ────────────────────────────────────────────────────
  function addFiles(incoming: FileList | File[]) {
    const next = [...files];
    for (const f of Array.from(incoming)) {
      if (!ALLOWED_EXT.includes(extOf(f.name))) {
        toast.error(`${f.name}: chỉ hỗ trợ .pdf và .md`);
        continue;
      }
      if (f.size > MAX_BYTES) {
        toast.error(`${f.name}: vượt 30MB`);
        continue;
      }
      if (next.some((x) => x.name === f.name && x.size === f.size)) continue;
      if (next.length >= MAX_FILES) {
        toast.error(`Tối đa ${MAX_FILES} file mỗi lần`);
        break;
      }
      next.push(f);
    }
    setFiles(next);
  }

  function removeFile(idx: number) {
    setFiles(files.filter((_, i) => i !== idx));
  }

  // ── Upload kickoff ────────────────────────────────────────────────────
  async function handleUpload() {
    if (files.length === 0) {
      toast.error("Chưa chọn file nào");
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      for (const f of files) form.append("files", f);

      const res = await apiFetch<UploadResponse>(
        `/projects/${projectId}/papers:upload`,
        { method: "POST", headers: authHeader, body: form },
      );

      const pending = res.drafts.filter(
        (d) => d.status === "pending" && d.project_paper_id,
      );
      for (const d of res.drafts) {
        if (d.status === "duplicate") toast.warning(`${d.filename}: đã có trong project`);
        else if (d.status === "rejected") toast.error(`${d.filename}: ${d.reason ?? "bị từ chối"}`);
      }

      if (pending.length === 0) {
        toast.error("Không có file hợp lệ để xử lý");
        setUploading(false);
        return;
      }

      const nameMap: Record<string, string> = {};
      for (const d of pending) nameMap[d.project_paper_id as string] = d.filename;
      setFilenames(nameMap);
      setExpandedId(pending[0].project_paper_id as string);
      setPhase("confirm");
      setIngesting(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Tải lên thất bại");
    } finally {
      setUploading(false);
    }
  }

  // ── Poll ingest status while in confirm phase ─────────────────────────
  useEffect(() => {
    if (phase !== "confirm" || !ingesting) return;
    const ids = Object.keys(filenames);
    if (ids.length === 0) return;

    let active = true;
    let attempts = 0;
    const MAX_ATTEMPTS = 48; // ~2 minutes at 2.5s — give up so the modal never hangs

    const finalize = (items: UploadStatusItem[]) => {
      setRows(
        items.map((it) => ({
          projectPaperId: it.project_paper_id,
          filename: filenames[it.project_paper_id] ?? "",
          fullTextStatus: it.full_text_status,
          title: it.title ?? "",
          authors: (it.authors ?? []).map((a) => a.name).join(", "),
          year: it.year != null ? String(it.year) : "",
          venue: it.venue ?? "",
          abstract: it.abstract ?? "",
        })),
      );
      setIngesting(false);
    };

    const poll = async () => {
      attempts += 1;
      try {
        const items = await apiFetch<UploadStatusItem[]>(
          `/projects/${projectId}/papers:upload-status?ids=${ids.join(",")}`,
          { headers: authHeader },
        );
        if (!active) return;
        const allDone = items.length > 0 && items.every((it) => TERMINAL.has(it.full_text_status ?? ""));
        if (allDone) {
          finalize(items);
        } else if (attempts >= MAX_ATTEMPTS) {
          toast.warning("Một số file xử lý quá lâu — bạn có thể nhập tay phần còn lại.");
          finalize(items);
        }
      } catch {
        if (active && attempts >= MAX_ATTEMPTS) {
          toast.error("Không lấy được trạng thái xử lý. Vui lòng thử lại.");
          setIngesting(false);
        }
        // otherwise transient — keep polling
      }
    };
    void poll();
    const interval = setInterval(poll, 2500);
    return () => {
      active = false;
      clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, ingesting, projectId]);

  function patchRow(id: string, patch: Partial<DraftRow>) {
    setRows((rs) => rs.map((r) => (r.projectPaperId === id ? { ...r, ...patch } : r)));
  }

  // ── Confirm / discard ─────────────────────────────────────────────────
  async function handleConfirm() {
    if (rows.some((r) => !r.title.trim())) {
      toast.error("Mỗi bài báo cần có tiêu đề");
      return;
    }
    setSubmitting(true);
    try {
      const items: ConfirmUploadItem[] = rows.map((r) => {
        const parsedYear = parseInt(r.year.trim(), 10);
        return {
          project_paper_id: r.projectPaperId,
          title: r.title.trim(),
          authors: r.authors
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
            .map((name) => ({ name })),
          year: Number.isFinite(parsedYear) ? parsedYear : null,
          venue: r.venue.trim() || null,
          abstract: r.abstract.trim() || null,
        };
      });
      await apiFetch(`/projects/${projectId}/papers:confirm-uploads`, {
        method: "POST",
        headers: authHeader,
        body: JSON.stringify({ items }),
      });
      toast.success(`Đã lưu ${items.length} bài báo & bắt đầu sinh Matrix`);
      onConfirmed();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Lưu thất bại");
      setSubmitting(false);
    }
  }

  async function handleCancel() {
    const ids = Object.keys(filenames);
    if (phase === "confirm" && ids.length > 0) {
      try {
        await apiFetch(`/projects/${projectId}/papers:discard-uploads`, {
          method: "POST",
          headers: authHeader,
          body: JSON.stringify({ project_paper_ids: ids }),
        });
      } catch {
        // best-effort cleanup
      }
    }
    onClose();
  }

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm animate-fade-in"
      onClick={(e) => {
        if (e.target === overlayRef.current && phase === "select" && !uploading) onClose();
      }}
    >
      <div
        className="w-full max-w-[600px] max-h-[88vh] overflow-y-auto rounded-[16px] bg-surface-card p-8 shadow-xl animate-scale-in"
        style={{ border: "1px solid var(--hairline)" }}
      >
        <div className="mb-2 flex items-center justify-between">
          <h2
            className="font-display text-[22px] font-bold leading-[1.2] text-ink"
            style={{ letterSpacing: "-0.5px" }}
          >
            {phase === "select" ? "Tải bài báo lên" : `Xác nhận thông tin · ${rows.length || "…"} bài báo`}
          </h2>
          <button
            onClick={handleCancel}
            className="flex h-[32px] w-[32px] items-center justify-center rounded-full text-charcoal hover:bg-surface-bone hover:text-ink transition-colors"
          >
            <X size={16} weight="bold" />
          </button>
        </div>

        {phase === "select" ? (
          <>
            <p className="mb-5 text-sm leading-[1.6] text-charcoal">
              Tối đa {MAX_FILES} file mỗi lần · Hỗ trợ <b>PDF</b> và <b>Markdown</b> · &lt; 30MB / file
            </p>

            <input
              ref={inputRef}
              type="file"
              multiple
              accept=".pdf,.md,application/pdf,text/markdown"
              className="hidden"
              onChange={(e) => {
                if (e.target.files) addFiles(e.target.files);
                e.target.value = "";
              }}
            />

            <div
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files) addFiles(e.dataTransfer.files);
              }}
              className="flex cursor-pointer flex-col items-center justify-center rounded-[13px] border-2 border-dashed px-6 py-8 text-center transition-colors hover:bg-surface-bone"
              style={{ borderColor: "var(--hairline)" }}
            >
              <UploadSimple size={30} className="text-primary" weight="bold" />
              <p className="mt-2 font-ui text-sm font-semibold text-ink">
                Kéo thả file vào đây, hoặc bấm để chọn
              </p>
              <p className="mt-1 text-[12px] text-ash">{files.length}/{MAX_FILES} file đã chọn</p>
            </div>

            {files.length > 0 && (
              <div className="mt-4 space-y-2">
                {files.map((f, i) => (
                  <div
                    key={`${f.name}-${i}`}
                    className="flex items-center gap-3 rounded-[10px] px-3 py-2"
                    style={{ border: "1px solid var(--hairline)" }}
                  >
                    <span
                      className={`font-ui rounded-[6px] px-2 py-0.5 text-[10px] font-bold ${
                        extOf(f.name) === ".pdf"
                          ? "bg-red-50 text-red-600"
                          : "bg-sky-50 text-sky-700"
                      }`}
                    >
                      {extOf(f.name) === ".pdf" ? "PDF" : "MD"}
                    </span>
                    <span className="font-ui min-w-0 flex-1 truncate text-[13px] font-medium text-ink">
                      {f.name}
                    </span>
                    <span className="text-[12px] text-ash">{(f.size / 1024 / 1024).toFixed(1)} MB</span>
                    <button
                      onClick={() => removeFile(i)}
                      className="text-ash hover:text-error transition-colors"
                      aria-label={`Bỏ ${f.name}`}
                    >
                      <Trash size={14} weight="bold" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="mt-4 rounded-[11px] bg-emerald-50/60 px-4 py-3 text-[12px] text-emerald-800">
              Sau khi tải lên, mỗi file tự động: <b>Ingest full text → AI trích metadata → Xác nhận → Sinh Matrix</b>
            </div>

            <div className="mt-6 flex gap-3">
              <button
                type="button"
                onClick={handleCancel}
                className="font-ui h-[44px] flex-1 rounded-full bg-surface-bone text-sm font-semibold text-charcoal hover:text-ink transition-colors"
              >
                Hủy
              </button>
              <button
                type="button"
                onClick={handleUpload}
                disabled={uploading || files.length === 0}
                className="font-ui inline-flex h-[44px] flex-1 items-center justify-center gap-2 rounded-full bg-primary text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50"
              >
                {uploading ? (
                  <>
                    <CircleNotch size={16} weight="bold" className="animate-spin" /> Đang tải…
                  </>
                ) : (
                  `Tải lên & xử lý${files.length ? ` (${files.length})` : ""}`
                )}
              </button>
            </div>
          </>
        ) : ingesting ? (
          <div className="flex flex-col items-center justify-center py-14 text-center">
            <CircleNotch size={34} weight="bold" className="animate-spin text-primary" />
            <p className="mt-4 font-ui text-sm font-semibold text-ink">Đang trích xuất full text…</p>
            <p className="mt-1 text-[12px] text-ash">
              Đang đọc {Object.keys(filenames).length} file và điền metadata, vui lòng đợi.
            </p>
          </div>
        ) : (
          <>
            <p className="mb-3 text-sm leading-[1.6] text-charcoal">
              AI đã điền metadata từ nội dung mỗi file — kiểm tra/sửa rồi lưu một lần.
            </p>

            <div className="space-y-3">
              {rows.map((r, idx) => {
                const open = expandedId === r.projectPaperId;
                const failed = r.fullTextStatus !== "completed";
                return (
                  <div
                    key={r.projectPaperId}
                    className="rounded-[12px] p-4"
                    style={{ border: "1px solid var(--hairline)", background: "var(--canvas)" }}
                  >
                    <button
                      type="button"
                      onClick={() => setExpandedId(open ? null : r.projectPaperId)}
                      className="flex w-full items-center gap-2 text-left"
                    >
                      <span className="font-ui rounded-[6px] bg-primary px-2 py-0.5 text-[11px] font-bold text-on-primary">
                        {idx + 1}/{rows.length}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="font-ui block truncate text-[13px] font-semibold text-ink">
                          {r.title || r.filename}
                        </span>
                        <span className="font-ui block truncate text-[11px] text-ash">{r.filename}</span>
                      </span>
                      {failed ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-600">
                          <WarningCircle size={13} weight="fill" /> trích xuất lỗi
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600">
                          <CheckCircle size={13} weight="fill" /> đã trích xuất
                        </span>
                      )}
                      <CaretDown
                        size={14}
                        weight="bold"
                        className={`text-ash transition-transform ${open ? "rotate-180" : ""}`}
                      />
                    </button>

                    {open && (
                      <div className="mt-3 space-y-3">
                        <Field label="Tiêu đề *">
                          <input
                            value={r.title}
                            onChange={(e) => patchRow(r.projectPaperId, { title: e.target.value })}
                            className={IPT}
                            style={IPT_STYLE}
                          />
                        </Field>
                        <div className="flex gap-3">
                          <Field label="Tác giả" className="flex-1">
                            <input
                              value={r.authors}
                              placeholder="Tên cách nhau bởi dấu phẩy"
                              onChange={(e) => patchRow(r.projectPaperId, { authors: e.target.value })}
                              className={IPT}
                              style={IPT_STYLE}
                            />
                          </Field>
                          <Field label="Năm" className="w-[110px]">
                            <input
                              value={r.year}
                              inputMode="numeric"
                              onChange={(e) => patchRow(r.projectPaperId, { year: e.target.value })}
                              className={IPT}
                              style={IPT_STYLE}
                            />
                          </Field>
                        </div>
                        <Field label="Nơi công bố (Venue)">
                          <input
                            value={r.venue}
                            onChange={(e) => patchRow(r.projectPaperId, { venue: e.target.value })}
                            className={IPT}
                            style={IPT_STYLE}
                          />
                        </Field>
                        <Field label="Tóm tắt (Abstract)">
                          <textarea
                            value={r.abstract}
                            onChange={(e) => patchRow(r.projectPaperId, { abstract: e.target.value })}
                            rows={4}
                            className={`${IPT} resize-none`}
                            style={IPT_STYLE}
                          />
                        </Field>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="mt-6 flex gap-3">
              <button
                type="button"
                onClick={handleCancel}
                disabled={submitting}
                className="font-ui h-[44px] flex-1 rounded-full bg-surface-bone text-sm font-semibold text-charcoal hover:text-ink transition-colors disabled:opacity-50"
              >
                Hủy
              </button>
              <button
                type="button"
                onClick={handleConfirm}
                disabled={submitting || rows.length === 0}
                className="font-ui inline-flex h-[44px] flex-1 items-center justify-center gap-2 rounded-full bg-primary text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50"
              >
                {submitting ? (
                  <>
                    <CircleNotch size={16} weight="bold" className="animate-spin" /> Đang lưu…
                  </>
                ) : (
                  `Lưu tất cả (${rows.length}) & sinh Matrix`
                )}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  children,
  className = "",
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1.5 block font-ui text-[12px] font-semibold text-charcoal">{label}</span>
      {children}
    </label>
  );
}
