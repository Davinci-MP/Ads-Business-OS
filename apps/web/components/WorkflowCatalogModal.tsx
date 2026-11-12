"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  WorkflowTemplateItem,
  dispatchControlHubCommand,
  getWorkflowTemplates,
} from "../lib/api";
import { MonoIcon } from "./mono-icon";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  selectedAccountIds: string[];
  onWorkflowComplete?: (msg: string) => void;
};

const CATEGORIES = [
  { id: "ALL", label: "Tất cả" },
  { id: "Quản lý TKQC", label: "Quản lý TKQC" },
  { id: "Bảo mật BM", label: "Bảo mật BM" },
  { id: "Nuôi & Kháng Page", label: "Nuôi & Kháng Page" },
  { id: "Phân phối Pixel", label: "Phân phối Pixel" },
  { id: "Lên Camp & Boost Post", label: "Lên Camp & Boost Post" },
  { id: "Thanh toán & Thẻ", label: "Thanh toán & Thẻ" },
];

export default function WorkflowCatalogModal({
  isOpen,
  onClose,
  selectedAccountIds,
  onWorkflowComplete,
}: Props) {
  const [workflows, setWorkflows] = useState<WorkflowTemplateItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeCategory, setActiveCategory] = useState("ALL");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowTemplateItem | null>(null);
  const [executing, setExecuting] = useState(false);
  const [progress, setProgress] = useState<{ step: number; total: number; action: string } | null>(null);
  const [feedback, setFeedback] = useState<{ text: string; error?: boolean } | null>(null);

  useEffect(() => {
    if (isOpen) {
      void loadWorkflows();
    }
  }, [isOpen]);

  const loadWorkflows = async () => {
    setLoading(true);
    try {
      const res = await getWorkflowTemplates();
      setWorkflows(res.workflows || []);
    } catch {
      // Fallback
    } finally {
      setLoading(false);
    }
  };

  const filteredWorkflows = useMemo(() => {
    return workflows.filter((w) => {
      const matchesCategory =
        activeCategory === "ALL" || w.category.toLowerCase().includes(activeCategory.toLowerCase());
      const matchesSearch =
        !searchTerm ||
        w.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        w.code.toLowerCase().includes(searchTerm.toLowerCase());
      return matchesCategory && matchesSearch;
    });
  }, [workflows, activeCategory, searchTerm]);

  const handleRunWorkflow = async (workflow: WorkflowTemplateItem) => {
    if (selectedAccountIds.length === 0) {
      setFeedback({
        text: "Vui lòng chọn ít nhất 1 tài khoản hoặc tài sản để chạy kịch bản.",
        error: true,
      });
      return;
    }

    setSelectedWorkflow(workflow);
    setExecuting(true);
    setFeedback(null);

    const steps = workflow.steps || [];
    const totalSteps = steps.length;

    try {
      // Execute each step sequentially with jitter delay
      for (let i = 0; i < totalSteps; i++) {
        const step = steps[i];
        setProgress({
          step: i + 1,
          total: totalSteps,
          action: (step.label as string) || (step.action as string) || `Bước ${i + 1}`,
        });

        // Dispatch command to browser nodes
        await dispatchControlHubCommand({
          command: String(step.action || "WORKFLOW_STEP"),
          payload: {
            workflow_code: workflow.code,
            step_index: i,
            step_action: step.action,
            account_ids: selectedAccountIds,
          },
        });

        // Jitter simulation delay between min and max ms
        const jitter = Math.floor(
          Math.random() * (workflow.jitter_max_ms - workflow.jitter_min_ms + 1) +
            workflow.jitter_min_ms
        );
        await new Promise((resolve) => setTimeout(resolve, Math.min(jitter, 800)));
      }

      setFeedback({
        text: ` Đã thực thi hoàn tất kịch bản [${workflow.name}] cho ${selectedAccountIds.length} tài sản!`,
      });
      if (onWorkflowComplete) {
        onWorkflowComplete(`Kịch bản ${workflow.name} hoàn tất.`);
      }
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi khi chạy kịch bản.",
        error: true,
      });
    } finally {
      setExecuting(false);
      setProgress(null);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in"
      onMouseDown={onClose}
    >
      <div
        className="w-full max-w-4xl max-h-[90vh] flex flex-col rounded-2xl border border-slate-800 bg-[#0f172a] shadow-2xl overflow-hidden"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* HEADER */}
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4 bg-[#111827]">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/10 text-xl text-indigo-400 border border-indigo-500/20">
              <MonoIcon name="campaign" className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">
                Kho 69+ Kịch Bản Tự Động Hóa Vận Hành (Pillar 2 Workflow)
              </h2>
              <p className="text-xs text-slate-400">
                Áp dụng tuần tự với Jitter Anti-Ban cho {selectedAccountIds.length} tài sản đã chọn
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <MonoIcon name="close" className="h-4 w-4" />
          </button>
        </div>

        {/* FEEDBACK & PROGRESS */}
        {feedback && (
          <div
            className={`mx-6 mt-4 rounded-xl border px-4 py-2.5 text-xs font-medium flex items-center justify-between ${
              feedback.error
                ? "border-rose-500/30 bg-rose-950/20 text-rose-300"
                : "border-emerald-500/30 bg-emerald-950/20 text-emerald-300"
            }`}
          >
            <span>{feedback.text}</span>
            <button onClick={() => setFeedback(null)} className="text-slate-400 hover:text-white">
              <MonoIcon name="close" className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {progress && (
          <div className="mx-6 mt-3 rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-3.5 space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-semibold text-indigo-300">
                Đang thực hiện bước {progress.step}/{progress.total}: {progress.action}
              </span>
              <span className="text-slate-400 font-mono">
                {Math.round((progress.step / progress.total) * 100)}%
              </span>
            </div>
            <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 transition-all duration-300"
                style={{ width: `${(progress.step / progress.total) * 100}%` }}
              />
            </div>
          </div>
        )}

        {/* CONTROLS (SEARCH & CATEGORIES) */}
        <div className="p-6 border-b border-slate-800/80 bg-slate-950/40 space-y-3">
          <div className="flex gap-3">
            <div className="relative flex-1">
              <input
                type="text"
                placeholder="Tìm kịch bản theo tên, mã (VD: WF-ACT, Đổi tên, Camp, Pixel)..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full rounded-xl border border-slate-800 bg-slate-900 px-4 py-2 text-xs text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <span className="text-xs font-mono text-slate-400 self-center">
              {filteredWorkflows.length} kịch bản
            </span>
          </div>

          {/* Category Tabs */}
          <div className="flex flex-wrap gap-1.5">
            {CATEGORIES.map((cat) => (
              <button
                key={cat.id}
                type="button"
                onClick={() => setActiveCategory(cat.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                  activeCategory === cat.id
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "border border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800"
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>
        </div>

        {/* WORKFLOWS GRID */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-xs text-slate-400">
              Đang tải danh mục kịch bản tự động...
            </div>
          ) : filteredWorkflows.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center text-xs text-slate-500">
              <p>Không tìm thấy kịch bản nào phù hợp.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {filteredWorkflows.map((w) => (
                <div
                  key={w.id}
                  className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 flex flex-col justify-between hover:border-indigo-500/50 hover:bg-slate-900 transition-all space-y-3"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-950/80 border border-indigo-500/30 text-indigo-300">
                        {w.code}
                      </span>
                      <span className="text-[10px] text-slate-400">
                        {w.steps?.length || 0} bước
                      </span>
                    </div>
                    <h4 className="text-xs font-bold text-white leading-tight">
                      {w.name}
                    </h4>
                    <p className="text-[11px] text-slate-400 font-mono">
                      Jitter: {w.jitter_min_ms}-{w.jitter_max_ms}ms
                    </p>
                  </div>

                  <button
                    type="button"
                    disabled={executing}
                    onClick={() => void handleRunWorkflow(w)}
                    className="w-full rounded-lg bg-indigo-600/90 py-2 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition shadow-sm flex items-center justify-center gap-1.5"
                  >
                    <MonoIcon name="campaign" className="h-4 w-4" />
                    <span>Thực Thi Ngay</span>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* FOOTER */}
        <div className="border-t border-slate-800 bg-[#111827] px-6 py-3 flex items-center justify-between text-xs text-slate-400">
          <span>
            {selectedAccountIds.length > 0
              ? `Đang chọn ${selectedAccountIds.length} tài sản quảng cáo để áp dụng kịch bản.`
              : "Tick chọn các tài khoản trên bảng trước khi bấm Chạy kịch bản."}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-700 px-4 py-1.5 text-xs text-white hover:bg-slate-800 transition"
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}
