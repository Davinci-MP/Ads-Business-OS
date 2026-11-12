"use client";

import { useCallback, useEffect, useState } from "react";
import {
  deleteJson,
  fetchJson,
  fmtTime,
  fmtVnd,
  patchJson,
  postJson,
  type AutomationRule,
  type TelegramActivityLog,
  type TelegramConfigInfo,
  type TelegramFullStatus,
} from "../../lib/api";

export default function TelegramManagementPage() {
  // --- States: Data ---
  const [status, setStatus] = useState<TelegramFullStatus | null>(null);
  const [config, setConfig] = useState<TelegramConfigInfo | null>(null);
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [logs, setLogs] = useState<TelegramActivityLog[]>([]);
  const [loading, setLoading] = useState(true);

  // --- States: Forms & Actions ---
  const [testingConnection, setTestingConnection] = useState(false);
  const [evaluatingRules, setEvaluatingRules] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);

  // Form Config
  const [botTokenInput, setBotTokenInput] = useState("");
  const [adminChatIdInput, setAdminChatIdInput] = useState("");
  const [allowedChatsInput, setAllowedChatsInput] = useState("");
  const [webhookUrlInput, setWebhookUrlInput] = useState("");

  // Form Add Rule Modal
  const [showAddRuleModal, setShowAddRuleModal] = useState(false);
  const [ruleName, setRuleName] = useState("");
  const [ruleType, setRuleType] = useState("AUTO_PAUSE_SPEND_LIMIT");
  const [ruleThreshold, setRuleThreshold] = useState("5000000");
  const [ruleCurrency, setRuleCurrency] = useState("VND");
  const [ruleAction, setRuleAction] = useState("AUTO_PAUSE");
  const [creatingRule, setCreatingRule] = useState(false);

  // Interactive Command Runner
  const [consoleCmd, setConsoleCmd] = useState("/tk");
  const [consoleOutput, setConsoleOutput] = useState<string | null>(null);
  const [runningCmd, setRunningCmd] = useState(false);

  // --- Fetch Data ---
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [st, cfg, rls, lg] = await Promise.all([
        fetchJson<TelegramFullStatus>("/telegram/status"),
        fetchJson<TelegramConfigInfo>("/telegram/config"),
        fetchJson<AutomationRule[]>("/telegram/rules"),
        fetchJson<TelegramActivityLog[]>("/telegram/activity-logs?limit=30"),
      ]);
      setStatus(st);
      setConfig(cfg);
      setRules(rls);
      setLogs(lg);

      setAdminChatIdInput(cfg.admin_chat_id || "");
      setAllowedChatsInput(cfg.allowed_chat_ids || "");
      setWebhookUrlInput(cfg.webhook_url || "");
    } catch (err) {
      setToast({ ok: false, text: `Lỗi tải dữ liệu: ${err instanceof Error ? err.message : String(err)}` });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Toast auto-dismiss
  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 5000);
      return () => clearTimeout(t);
    }
  }, [toast]);

  // --- Handlers ---
  const handleTestConnection = async () => {
    setTestingConnection(true);
    try {
      const res = await postJson<{ success: boolean; message: string; bot: { username?: string; first_name?: string } }>(
        "/telegram/test-connection"
      );
      setToast({ ok: true, text: res.message });
      void loadData();
    } catch (err) {
      setToast({ ok: false, text: `Kiểm tra thất bại: ${err instanceof Error ? err.message : String(err)}` });
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingConfig(true);
    try {
      const res = await postJson<{ success: boolean; message: string }>("/telegram/config", {
        bot_token: botTokenInput.trim() || undefined,
        admin_chat_id: adminChatIdInput.trim() || undefined,
        allowed_chat_ids: allowedChatsInput.trim() || undefined,
        webhook_url: webhookUrlInput.trim() || undefined,
      });
      setToast({ ok: true, text: res.message });
      setBotTokenInput("");
      void loadData();
    } catch (err) {
      setToast({ ok: false, text: `Lỗi lưu cấu hình: ${err instanceof Error ? err.message : String(err)}` });
    } finally {
      setSavingConfig(false);
    }
  };

  const handleToggleRule = async (ruleId: number, current: boolean) => {
    try {
      await patchJson(`/telegram/rules/${ruleId}`, { is_enabled: !current });
      setRules((prev) => prev.map((r) => (r.id === ruleId ? { ...r, is_enabled: !current } : r)));
      setToast({ ok: true, text: `Đã ${!current ? "BẬT" : "TẮT"} quy tắc thành công!` });
    } catch (err) {
      setToast({ ok: false, text: `Lỗi đổi trạng thái quy tắc: ${err instanceof Error ? err.message : String(err)}` });
    }
  };

  const handleDeleteRule = async (ruleId: number, name: string) => {
    if (!confirm(`Bạn có chắc muốn xoá quy tắc '${name}'?`)) return;
    try {
      await deleteJson(`/telegram/rules/${ruleId}`);
      setRules((prev) => prev.filter((r) => r.id !== ruleId));
      setToast({ ok: true, text: `Đã xoá quy tắc '${name}'.` });
    } catch (err) {
      setToast({ ok: false, text: `Lỗi xoá quy tắc: ${err instanceof Error ? err.message : String(err)}` });
    }
  };

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreatingRule(true);
    try {
      const num = Number(ruleThreshold.replace(/\D/g, ""));
      await postJson("/telegram/rules", {
        name: ruleName.trim(),
        rule_type: ruleType,
        threshold: num,
        currency: ruleCurrency,
        action_type: ruleAction,
        is_enabled: true,
      });
      setShowAddRuleModal(false);
      setRuleName("");
      setToast({ ok: true, text: "Tạo quy tắc tự động hóa mới thành công!" });
      void loadData();
    } catch (err) {
      setToast({ ok: false, text: `Lỗi tạo quy tắc: ${err instanceof Error ? err.message : String(err)}` });
    } finally {
      setCreatingRule(false);
    }
  };

  const handleRunEvaluation = async () => {
    setEvaluatingRules(true);
    try {
      const res = await postJson<{ success: boolean; message: string; summary: { rules_checked: number; triggered_count: number } }>(
        "/telegram/rules/run-check"
      );
      setToast({ ok: true, text: ` ${res.message}` });
      void loadData();
    } catch (err) {
      setToast({ ok: false, text: `Lỗi chạy quy tắc: ${err instanceof Error ? err.message : String(err)}` });
    } finally {
      setEvaluatingRules(false);
    }
  };

  const handleRunConsoleCommand = async () => {
    if (!consoleCmd.trim()) return;
    setRunningCmd(true);
    try {
      const res = await postJson<{ command: string; response_text: string }>("/telegram/dispatch", {
        command: consoleCmd.trim(),
        actor: "admin_web_console",
      });
      setConsoleOutput(res.response_text);
      void loadData();
    } catch (err) {
      setConsoleOutput(` Lỗi thực thi: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setRunningCmd(false);
    }
  };

  return (
    <div
      className="w-full space-y-6"
      style={{
        color: "#F4F0E8",
        fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
      }}
    >
      {/* Toast Notification */}
      {toast && (
        <div
          style={{
            position: "fixed",
            bottom: 24,
            right: 24,
            zIndex: 9999,
            background: toast.ok ? "#13141C" : "#261318",
            color: toast.ok ? "#7EE8C0" : "#FF7D8C",
            border: `1px solid ${toast.ok ? "rgba(126,232,192,0.35)" : "rgba(255,125,140,0.35)"}`,
            padding: "12px 20px",
            borderRadius: 8,
            boxShadow: "0 10px 25px rgba(0,0,0,0.5)",
            fontSize: 13,
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <span>{toast.ok ? "" : ""}</span>
          <span>{toast.text}</span>
          <button
            onClick={() => setToast(null)}
            style={{ background: "none", border: 0, color: "inherit", cursor: "pointer", marginLeft: 8 }}
          >
            
          </button>
        </div>
      )}

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, letterSpacing: "-0.02em" }}>
               Trung tâm Điều khiển Telegram Bot &amp; Quy tắc Tự động hóa
            </h1>
            <span
              style={{
                background: status?.connection_ok ? "rgba(126,232,192,0.15)" : "rgba(255,178,107,0.15)",
                color: status?.connection_ok ? "#7EE8C0" : "#FFB26B",
                border: `1px solid ${status?.connection_ok ? "rgba(126,232,192,0.3)" : "rgba(255,178,107,0.3)"}`,
                borderRadius: 999,
                padding: "2px 10px",
                fontSize: 11,
                fontWeight: 700,
              }}
            >
              {status?.connection_ok ? "Đang kết nối (Live)" : "Chế độ Mock (Kiểm thử)"}
            </span>
          </div>
          <p style={{ margin: "6px 0 0", color: "rgba(244,240,232,0.6)", fontSize: 13 }}>
            Cấu hình Bot Telegram, bảo mật phân quyền Chat Whitelist và thiết lập các quy tắc cảnh báo, tự động tạm dừng campaign.
          </p>
        </div>

        <div style={{ display: "flex", gap: 10 }}>
          <button
            onClick={handleTestConnection}
            disabled={testingConnection}
            style={{
              background: "rgba(183,164,255,0.12)",
              color: "#B7A4FF",
              border: "1px solid rgba(183,164,255,0.3)",
              padding: "8px 16px",
              borderRadius: 6,
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span>{testingConnection ? "Đang thử…" : ""}</span>
            <span>Kiểm tra kết nối Bot</span>
          </button>

          <button
            onClick={() => void loadData()}
            style={{
              background: "#1A1B25",
              color: "#F4F0E8",
              border: "1px solid rgba(255,255,255,0.12)",
              padding: "8px 14px",
              borderRadius: 6,
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            Làm mới
          </button>
        </div>
      </div>

      {/* KPI Cards Bar */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14, marginBottom: 28 }}>
        <div style={{ background: "#13141C", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 10, padding: 16 }}>
          <div style={{ fontSize: 12, color: "rgba(244,240,232,0.5)" }}>Tên định danh Bot</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#fff", marginTop: 4 }}>
            {status?.bot_info?.username ? `@${status.bot_info.username}` : "Chưa liên kết"}
          </div>
          <div style={{ fontSize: 11, color: "#7EE8C0", marginTop: 2 }}>{status?.bot_info?.first_name || "Bot Mock"}</div>
        </div>

        <div style={{ background: "#13141C", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 10, padding: 16 }}>
          <div style={{ fontSize: 12, color: "rgba(244,240,232,0.5)" }}>Quy tắc tự động đang bật</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "#7EE8C0", marginTop: 4, fontFamily: "monospace" }}>
            {rules.filter((r) => r.is_enabled).length} / {rules.length}
          </div>
          <div style={{ fontSize: 11, color: "rgba(244,240,232,0.45)", marginTop: 2 }}>Đang bảo vệ thời gian thực</div>
        </div>

        <div style={{ background: "#13141C", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 10, padding: 16 }}>
          <div style={{ fontSize: 12, color: "rgba(244,240,232,0.5)" }}>Chat ID được phân quyền (Whitelist)</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "#B7A4FF", marginTop: 4, fontFamily: "monospace" }}>
            {status?.allowed_chat_ids_count ?? 0}
          </div>
          <div style={{ fontSize: 11, color: "rgba(244,240,232,0.45)", marginTop: 2 }}>
            Admin Chat: {status?.admin_chat_id || "Chưa gán"}
          </div>
        </div>

        <div style={{ background: "#13141C", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 10, padding: 16 }}>
          <div style={{ fontSize: 12, color: "rgba(244,240,232,0.5)" }}>Trạng thái Webhook</div>
          <div style={{ fontSize: 15, fontWeight: 700, color: "#fff", marginTop: 6 }}>
            {status?.webhook_info?.url ? "Đã bật Webhook" : "Chế độ Polling"}
          </div>
          <div style={{ fontSize: 11, color: "rgba(244,240,232,0.45)", marginTop: 2, fontFamily: "monospace" }}>
            Pending updates: {status?.webhook_info?.pending_update_count ?? 0}
          </div>
        </div>
      </div>

      {/* Grid: Main Control & Automation Rules */}
      <div style={{ display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: 24, marginBottom: 28 }}>
        {/* PHẦN 1: BẢNG QUY TẮC TỰ ĐỘNG HÓA (Automation Rules Builder) */}
        <div style={{ background: "#13141C", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <div>
              <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}> Quy tắc Tự động hóa (Automation Rules)</h2>
              <div style={{ fontSize: 12, color: "rgba(244,240,232,0.5)", marginTop: 2 }}>
                Tự động kiểm tra chi tiêu, tạm dừng chiến dịch và gửi thông báo khẩn cấp tới Telegram.
              </div>
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={handleRunEvaluation}
                disabled={evaluatingRules}
                style={{
                  background: "rgba(126,232,192,0.12)",
                  color: "#7EE8C0",
                  border: "1px solid rgba(126,232,192,0.3)",
                  padding: "6px 12px",
                  borderRadius: 6,
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {evaluatingRules ? "Đang quét…" : " Quét quy tắc ngay"}
              </button>

              <button
                onClick={() => setShowAddRuleModal(true)}
                style={{
                  background: "#B7A4FF",
                  color: "#0B0C12",
                  border: 0,
                  padding: "6px 12px",
                  borderRadius: 6,
                  fontSize: 12,
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                + Thêm quy tắc
              </button>
            </div>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, background: "transparent" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", color: "rgba(244,240,232,0.5)", textAlign: "left" }}>
                  <th style={{ padding: "8px 10px", fontWeight: 600 }}>Tên quy tắc</th>
                  <th style={{ padding: "8px 10px", fontWeight: 600 }}>Ngưỡng kích hoạt</th>
                  <th style={{ padding: "8px 10px", fontWeight: 600 }}>Hành động</th>
                  <th style={{ padding: "8px 10px", fontWeight: 600 }}>Lần chạy gần nhất</th>
                  <th style={{ padding: "8px 10px", fontWeight: 600, textAlign: "center" }}>Trạng thái</th>
                  <th style={{ padding: "8px 10px", fontWeight: 600, textAlign: "right" }}>Xoá</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((rule) => {
                  const isAutoPause = rule.action_type === "AUTO_PAUSE";

                  return (
                    <tr
                      key={rule.id}
                      style={{
                        borderBottom: "1px solid rgba(255,255,255,0.04)",
                        transition: "background 0.15s",
                      }}
                    >
                      <td style={{ padding: "12px 10px" }}>
                        <div style={{ fontWeight: 600, color: rule.is_enabled ? "#fff" : "rgba(244,240,232,0.4)" }}>
                          {rule.name}
                        </div>
                        <div style={{ fontSize: 11, color: "rgba(244,240,232,0.45)", marginTop: 2 }}>
                          Mã: <code style={{ fontFamily: "monospace" }}>{rule.rule_type}</code>
                        </div>
                      </td>

                      <td style={{ padding: "12px 10px", fontFamily: "monospace", fontSize: 13, fontWeight: 600, color: "#FFB26B" }}>
                        {rule.threshold > 0 ? `${fmtVnd(rule.threshold)} ${rule.currency}` : "Định kỳ"}
                      </td>

                      <td style={{ padding: "12px 10px" }}>
                        <span
                          style={{
                            display: "inline-block",
                            padding: "2px 8px",
                            borderRadius: 4,
                            fontSize: 11,
                            fontWeight: 700,
                            background: isAutoPause ? "rgba(255,125,140,0.15)" : "rgba(183,164,255,0.15)",
                            color: isAutoPause ? "#FF7D8C" : "#B7A4FF",
                            border: `1px solid ${isAutoPause ? "rgba(255,125,140,0.3)" : "rgba(183,164,255,0.3)"}`,
                          }}
                        >
                          {isAutoPause ? " Tự động dừng" : " Báo Telegram"}
                        </span>
                      </td>

                      <td style={{ padding: "12px 10px", fontSize: 11, color: "rgba(244,240,232,0.5)" }}>
                        {rule.last_triggered_at ? fmtTime(rule.last_triggered_at) : "Chưa kích hoạt"}
                        <div style={{ fontFamily: "monospace", color: "rgba(244,240,232,0.35)", marginTop: 1 }}>
                          Trigger: {rule.trigger_count} lần
                        </div>
                      </td>

                      <td style={{ padding: "12px 10px", textAlign: "center" }}>
                        {/* Lucian-UXUI Stretchy Switch Toggle Inspired */}
                        <button
                          type="button"
                          role="switch"
                          aria-checked={rule.is_enabled}
                          onClick={() => void handleToggleRule(rule.id, rule.is_enabled)}
                          style={{
                            width: 44,
                            height: 24,
                            borderRadius: 999,
                            background: rule.is_enabled ? "#14B8A6" : "#252632",
                            border: "1px solid rgba(255,255,255,0.15)",
                            padding: 2,
                            position: "relative",
                            cursor: "pointer",
                            transition: "background 0.25s ease",
                            display: "inline-block",
                          }}
                        >
                          <span
                            style={{
                              display: "block",
                              width: 18,
                              height: 18,
                              borderRadius: 999,
                              background: "#fff",
                              position: "absolute",
                              top: 2,
                              left: rule.is_enabled ? 22 : 2,
                              transition: "left 0.25s cubic-bezier(0.34, 1.45, 0.64, 1)",
                              boxShadow: "0 2px 4px rgba(0,0,0,0.3)",
                            }}
                          />
                        </button>
                      </td>

                      <td style={{ padding: "12px 10px", textAlign: "right" }}>
                        <button
                          onClick={() => void handleDeleteRule(rule.id, rule.name)}
                          style={{
                            background: "none",
                            border: 0,
                            color: "rgba(255,125,140,0.7)",
                            cursor: "pointer",
                            fontSize: 14,
                          }}
                          title="Xoá quy tắc"
                        >
                          
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* PHẦN 2: CẤU HÌNH & KẾT NỐI BOT (Bot Config Form) */}
        <div style={{ background: "#13141C", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, padding: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 4px" }}> Cấu hình &amp; Phân quyền Telegram Bot</h2>
          <p style={{ margin: "0 0 16px", color: "rgba(244,240,232,0.5)", fontSize: 12 }}>
            Token được mã hóa Fernet server-side an toàn. Chỉ Chat ID có trong Whitelist mới được tương tác.
          </p>

          <form onSubmit={handleSaveConfig} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "rgba(244,240,232,0.75)", marginBottom: 4 }}>
                Telegram Bot Token
              </label>
              <input
                type="password"
                placeholder={config?.has_token ? "•••••••••••••••• (Đã lưu token an toàn)" : "Nhập bot token từ @BotFather..."}
                value={botTokenInput}
                onChange={(e) => setBotTokenInput(e.target.value)}
                style={{
                  width: "100%",
                  background: "#1A1B25",
                  border: "1px solid rgba(255,255,255,0.12)",
                  borderRadius: 6,
                  padding: "8px 12px",
                  color: "#fff",
                  fontSize: 13,
                  fontFamily: "monospace",
                }}
              />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "rgba(244,240,232,0.75)", marginBottom: 4 }}>
                  Admin Chat ID
                </label>
                <input
                  type="text"
                  placeholder="Ví dụ: 123456789"
                  value={adminChatIdInput}
                  onChange={(e) => setAdminChatIdInput(e.target.value)}
                  style={{
                    width: "100%",
                    background: "#1A1B25",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 6,
                    padding: "8px 12px",
                    color: "#fff",
                    fontSize: 13,
                    fontFamily: "monospace",
                  }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "rgba(244,240,232,0.75)", marginBottom: 4 }}>
                  Chat ID Whitelist (Cách nhau dấu phẩy)
                </label>
                <input
                  type="text"
                  placeholder="123456789, -100987654321"
                  value={allowedChatsInput}
                  onChange={(e) => setAllowedChatsInput(e.target.value)}
                  style={{
                    width: "100%",
                    background: "#1A1B25",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 6,
                    padding: "8px 12px",
                    color: "#fff",
                    fontSize: 13,
                    fontFamily: "monospace",
                  }}
                />
              </div>
            </div>

            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "rgba(244,240,232,0.75)", marginBottom: 4 }}>
                Webhook URL (Tùy chọn)
              </label>
              <input
                type="text"
                placeholder="https://your-domain.com/api/v1/telegram/webhook"
                value={webhookUrlInput}
                onChange={(e) => setWebhookUrlInput(e.target.value)}
                style={{
                  width: "100%",
                  background: "#1A1B25",
                  border: "1px solid rgba(255,255,255,0.12)",
                  borderRadius: 6,
                  padding: "8px 12px",
                  color: "#fff",
                  fontSize: 13,
                  fontFamily: "monospace",
                }}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 4 }}>
              <button
                type="submit"
                disabled={savingConfig}
                style={{
                  background: "#6A57F2",
                  color: "#fff",
                  border: 0,
                  borderRadius: 6,
                  padding: "8px 18px",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {savingConfig ? "Đang lưu…" : "Lưu cấu hình an toàn"}
              </button>
            </div>
          </form>

          {/* Quick Guide */}
          <div style={{ marginTop: 18, background: "#1A1B25", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 8, padding: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#FFB26B", marginBottom: 6 }}> Hướng dẫn lấy Chat ID Telegram:</div>
            <ol style={{ margin: 0, paddingLeft: 18, fontSize: 11, color: "rgba(244,240,232,0.65)", lineHeight: 1.6 }}>
              <li>Chat với bot <code>@userinfobot</code> hoặc <code>@getidsbot</code> trên Telegram để xem ID cá nhân.</li>
              <li>Nếu muốn bot gửi vào nhóm, thêm bot vào nhóm và lấy Chat ID dạng âm (ví dụ: <code>-100...</code>).</li>
              <li>Nhập các Chat ID vào ô Whitelist phía trên để cấp quyền điều khiển cho thành viên tin cậy.</li>
            </ol>
          </div>
        </div>
      </div>

      {/* Grid: Console Runner & Live Activity Logs */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        {/* Console Trực tiếp */}
        <div style={{ background: "#13141C", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, padding: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 4px" }}> Bảng điều khiển thử nghiệm (Web Console)</h2>
          <p style={{ margin: "0 0 14px", color: "rgba(244,240,232,0.5)", fontSize: 12 }}>
            Mô phỏng gửi lệnh bot như trên Telegram để kiểm tra phản hồi tức thì.
          </p>

          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <input
              type="text"
              value={consoleCmd}
              onChange={(e) => setConsoleCmd(e.target.value)}
              placeholder="Nhập lệnh: /tk, /baocao today, /status, /batcamp cmp_1001..."
              style={{
                flex: 1,
                background: "#07080D",
                border: "1px solid rgba(255,255,255,0.15)",
                borderRadius: 6,
                padding: "8px 12px",
                color: "#7EE8C0",
                fontSize: 13,
                fontFamily: "monospace",
              }}
            />
            <button
              onClick={handleRunConsoleCommand}
              disabled={runningCmd}
              style={{
                background: "#14B8A6",
                color: "#0B0C12",
                border: 0,
                borderRadius: 6,
                padding: "8px 16px",
                fontSize: 13,
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              {runningCmd ? "Đang chạy…" : "Gửi lệnh"}
            </button>
          </div>

          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
            {["/tk", "/baocao today", "/status", "/help"].map((cmd) => (
              <button
                key={cmd}
                onClick={() => setConsoleCmd(cmd)}
                style={{
                  background: "#1A1B25",
                  color: "#B7A4FF",
                  border: "1px solid rgba(183,164,255,0.2)",
                  borderRadius: 4,
                  padding: "3px 8px",
                  fontSize: 11,
                  fontFamily: "monospace",
                  cursor: "pointer",
                }}
              >
                {cmd}
              </button>
            ))}
          </div>

          <div
            style={{
              background: "#07080D",
              border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: 8,
              padding: 14,
              minHeight: 180,
              maxHeight: 280,
              overflowY: "auto",
              fontFamily: "monospace",
              fontSize: 12,
              lineHeight: 1.6,
              color: "#E2E8F0",
              whiteSpace: "pre-wrap",
            }}
          >
            {consoleOutput ? (
              <div dangerouslySetInnerHTML={{ __html: consoleOutput }} />
            ) : (
              <span style={{ color: "rgba(244,240,232,0.3)" }}>
                Nhấn [Gửi lệnh] để kiểm tra kết quả phản hồi của Bot Agent tại đây…
              </span>
            )}
          </div>
        </div>

        {/* Nhật ký tương tác (Activity Logs) */}
        <div style={{ background: "#13141C", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}> Nhật ký hoạt động Bot gần đây</h2>
            <span style={{ fontSize: 12, color: "rgba(244,240,232,0.45)", fontFamily: "monospace" }}>{logs.length} sự kiện</span>
          </div>

          <div style={{ maxHeight: 310, overflowY: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, background: "transparent" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", color: "rgba(244,240,232,0.45)", textAlign: "left" }}>
                  <th style={{ padding: "6px 8px" }}>Thời gian</th>
                  <th style={{ padding: "6px 8px" }}>Người gửi</th>
                  <th style={{ padding: "6px 8px" }}>Lệnh</th>
                  <th style={{ padding: "6px 8px" }}>Kết quả</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => {
                  const isOk = log.status === "SUCCESS";
                  const isReject = log.status === "REJECTED";

                  return (
                    <tr key={log.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                      <td style={{ padding: "8px 8px", color: "rgba(244,240,232,0.5)", fontSize: 11, fontFamily: "monospace" }}>
                        {log.created_at ? fmtTime(log.created_at) : "—"}
                      </td>
                      <td style={{ padding: "8px 8px" }}>
                        <b>{log.username}</b>
                        <div style={{ fontSize: 10, color: "rgba(244,240,232,0.35)", fontFamily: "monospace" }}>
                          ID: {log.chat_id}
                        </div>
                      </td>
                      <td style={{ padding: "8px 8px", fontFamily: "monospace", color: "#B7A4FF" }}>{log.command}</td>
                      <td style={{ padding: "8px 8px" }}>
                        <span
                          style={{
                            padding: "2px 6px",
                            borderRadius: 4,
                            fontSize: 10,
                            fontWeight: 700,
                            background: isOk ? "rgba(126,232,192,0.15)" : isReject ? "rgba(255,178,107,0.15)" : "rgba(255,125,140,0.15)",
                            color: isOk ? "#7EE8C0" : isReject ? "#FFB26B" : "#FF7D8C",
                          }}
                        >
                          {isOk ? "Thành công" : isReject ? "Từ chối" : "Lỗi"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
                {logs.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{ padding: "20px 8px", textAlign: "center", color: "rgba(244,240,232,0.4)" }}>
                      Chưa có nhật ký hoạt động nào.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* MODAL: Thêm quy tắc tự động hóa */}
      {showAddRuleModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.75)",
            backdropFilter: "blur(4px)",
            display: "grid",
            placeItems: "center",
            zIndex: 9999,
            padding: 16,
          }}
        >
          <div
            style={{
              background: "#13141C",
              border: "1px solid rgba(255,255,255,0.15)",
              borderRadius: 12,
              padding: 24,
              maxWidth: 500,
              width: "100%",
              boxShadow: "0 20px 50px rgba(0,0,0,0.8)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: "#fff" }}>
                 Thêm Quy tắc Tự động hóa mới
              </h3>
              <button
                onClick={() => setShowAddRuleModal(false)}
                style={{ background: "none", border: 0, color: "rgba(244,240,232,0.5)", fontSize: 18, cursor: "pointer" }}
              >
                
              </button>
            </div>

            <form onSubmit={handleCreateRule} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "rgba(244,240,232,0.75)", marginBottom: 4 }}>
                  Tên quy tắc *
                </label>
                <input
                  type="text"
                  required
                  placeholder="Ví dụ: Tự động dừng camp khi chi tiêu vượt 8 triệu..."
                  value={ruleName}
                  onChange={(e) => setRuleName(e.target.value)}
                  style={{
                    width: "100%",
                    background: "#1A1B25",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 6,
                    padding: "8px 12px",
                    color: "#fff",
                    fontSize: 13,
                  }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "rgba(244,240,232,0.75)", marginBottom: 4 }}>
                  Loại quy tắc
                </label>
                <select
                  value={ruleType}
                  onChange={(e) => {
                    const val = e.target.value;
                    setRuleType(val);
                    if (val === "ALERT_LOW_VCC_BALANCE") {
                      setRuleCurrency("USD");
                      setRuleThreshold("50");
                      setRuleAction("TELEGRAM_ALERT");
                    } else if (val === "AUTO_PAUSE_SPEND_LIMIT") {
                      setRuleCurrency("VND");
                      setRuleThreshold("10000000");
                      setRuleAction("AUTO_PAUSE");
                    }
                  }}
                  style={{
                    width: "100%",
                    background: "#1A1B25",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 6,
                    padding: "8px 12px",
                    color: "#fff",
                    fontSize: 13,
                  }}
                >
                  <option value="AUTO_PAUSE_SPEND_LIMIT">Tự động tạm dừng chiến dịch khi chi tiêu vượt hạn mức</option>
                  <option value="ALERT_LOW_VCC_BALANCE">Cảnh báo số dư thẻ ảo VCC PingPong thấp</option>
                  <option value="ALERT_HIGH_DRIFT_SPEND">Cảnh báo tiền trôi bất thường vượt mức</option>
                  <option value="DAILY_REPORT_SCHEDULE">Báo cáo tóm tắt hiệu suất hàng ngày</option>
                </select>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1.2fr 0.8fr", gap: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "rgba(244,240,232,0.75)", marginBottom: 4 }}>
                    Ngưỡng kích hoạt
                  </label>
                  <input
                    type="text"
                    required
                    value={ruleThreshold}
                    onChange={(e) => setRuleThreshold(e.target.value)}
                    style={{
                      width: "100%",
                      background: "#1A1B25",
                      border: "1px solid rgba(255,255,255,0.12)",
                      borderRadius: 6,
                      padding: "8px 12px",
                      color: "#fff",
                      fontSize: 13,
                      fontFamily: "monospace",
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "rgba(244,240,232,0.75)", marginBottom: 4 }}>
                    Đơn vị tiền tệ
                  </label>
                  <select
                    value={ruleCurrency}
                    onChange={(e) => setRuleCurrency(e.target.value)}
                    style={{
                      width: "100%",
                      background: "#1A1B25",
                      border: "1px solid rgba(255,255,255,0.12)",
                      borderRadius: 6,
                      padding: "8px 12px",
                      color: "#fff",
                      fontSize: 13,
                    }}
                  >
                    <option value="VND">VND (Việt Nam Đồng)</option>
                    <option value="USD">USD (Đô la Mỹ)</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "rgba(244,240,232,0.75)", marginBottom: 4 }}>
                  Hành động thực thi
                </label>
                <select
                  value={ruleAction}
                  onChange={(e) => setRuleAction(e.target.value)}
                  style={{
                    width: "100%",
                    background: "#1A1B25",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 6,
                    padding: "8px 12px",
                    color: "#fff",
                    fontSize: 13,
                  }}
                >
                  <option value="AUTO_PAUSE">Tự động chuyển chiến dịch sang PAUSED và báo Telegram</option>
                  <option value="TELEGRAM_ALERT">Chỉ gửi tin nhắn cảnh báo tới Telegram Admin</option>
                  <option value="DAILY_DIGEST">Gửi báo cáo tóm tắt định kỳ</option>
                </select>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 8 }}>
                <button
                  type="button"
                  onClick={() => setShowAddRuleModal(false)}
                  style={{
                    background: "#1A1B25",
                    color: "rgba(244,240,232,0.7)",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 6,
                    padding: "8px 16px",
                    fontSize: 13,
                    cursor: "pointer",
                  }}
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={creatingRule}
                  style={{
                    background: "#B7A4FF",
                    color: "#0B0C12",
                    border: 0,
                    borderRadius: 6,
                    padding: "8px 18px",
                    fontSize: 13,
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                >
                  {creatingRule ? "Đang tạo…" : "Tạo quy tắc ngay"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
