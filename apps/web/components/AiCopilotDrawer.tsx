"use client";

import { useEffect, useRef, useState } from "react";
import { getCopilotStatus, sendCopilotChat, type CopilotStatus } from "../lib/api";
import { MonoIcon } from "./mono-icon";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  tools?: string[];
  timestamp: string;
}

interface AiCopilotDrawerProps {
  open: boolean;
  onClose: () => void;
}

const QUICK_PROMPTS = [
  "📊 Báo cáo tổng quan chi tiêu hệ thống hôm nay",
  "🚀 Các chiến dịch nào đang hoạt động?",
  "💼 Danh sách khách hàng và công nợ tạm ứng",
  "🛡️ Kiểm tra tình trạng dàn VIA Profiles",
];

export function AiCopilotDrawer({ open, onClose }: AiCopilotDrawerProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<CopilotStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) {
      getCopilotStatus()
        .then((s) => setStatus(s))
        .catch(() => {});
      textareaRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  const handleSend = async (textToSend?: string) => {
    const query = (textToSend || input).trim();
    if (!query || loading) return;

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: "user",
      content: query,
      timestamp: new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }),
    };

    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput("");
    setError(null);
    setLoading(true);

    try {
      const historyPayload = messages.slice(-8).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await sendCopilotChat(query, historyPayload);

      const aiMsg: Message = {
        id: `a-${Date.now()}`,
        role: "assistant",
        content: res.reply,
        tools: res.tools_used,
        timestamp: new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages([...nextMessages, aiMsg]);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : "Có lỗi xảy ra khi xử lý phản hồi từ AI Copilot.";
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleClearChat = () => {
    setMessages([]);
    setError(null);
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className={`copilot-backdrop ${open ? "open" : ""}`}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <aside
        className={`copilot-drawer ${open ? "open" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label="ADSOS AI Copilot"
      >
        {/* Header (Twenty Style) */}
        <header className="copilot-header">
          <div className="copilot-brand">
            <div className="copilot-avatar">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
              </svg>
            </div>
            <div>
              <div className="copilot-title">
                <strong>ADSOS Copilot</strong>
                <span className="copilot-badge">
                  {status?.provider === "ollama" ? "Ollama Local" : "Gemini 2.0 Flash"}
                </span>
              </div>
              <small className="copilot-subtitle">
                <span className="copilot-indicator online" />
                Orchestrator {status?.staff_tools_count ? `(${status.staff_tools_count} Tools)` : "Ready"}
              </small>
            </div>
          </div>

          <div className="copilot-header-actions">
            {messages.length > 0 && (
              <button
                className="btn icon-btn"
                onClick={handleClearChat}
                title="Làm mới hội thoại"
                aria-label="Làm mới hội thoại"
              >
                <MonoIcon name="refresh" width={16} height={16} />
              </button>
            )}
            <button
              className="btn icon-btn"
              onClick={onClose}
              title="Đóng ngăn kéo Copilot (Esc)"
              aria-label="Đóng ngăn kéo Copilot"
            >
              <MonoIcon name="close" width={16} height={16} />
            </button>
          </div>
        </header>

        {/* Message Stream */}
        <div className="copilot-body">
          {messages.length === 0 ? (
            <div className="copilot-welcome">
              <div className="copilot-welcome-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M12 2a8 8 0 0 0-8 8c0 3.5 2.5 6.5 6 7.5V20a2 2 0 0 0 2 2h0a2 2 0 0 0 2-2v-2.5c3.5-1 6-4 6-7.5a8 8 0 0 0-8-8z"/>
                  <path d="M9 10h.01M15 10h.01M9.5 14a3.5 3.5 0 0 0 5 0"/>
                </svg>
              </div>
              <h3>Xin chào! Tôi có thể giúp gì cho bạn?</h3>
              <p>
                Trợ lý AI Copilot kết nối trực tiếp với hệ điều hành Ads Business OS. Tôi có thể tra cứu chi tiêu, chiến dịch, dàn VIA và số dư khách hàng.
              </p>

              <div className="copilot-quick-chips">
                <span className="copilot-chips-label">Gợi ý tác vụ nhanh:</span>
                {QUICK_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    className="copilot-chip"
                    onClick={() => handleSend(prompt)}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="copilot-messages">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`copilot-bubble-wrap ${msg.role === "user" ? "user-wrap" : "ai-wrap"}`}
                >
                  {msg.role === "assistant" && (
                    <div className="copilot-msg-avatar">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
                      </svg>
                    </div>
                  )}

                  <div className={`copilot-bubble ${msg.role === "user" ? "user-bubble" : "ai-bubble"}`}>
                    {msg.tools && msg.tools.length > 0 && (
                      <div className="copilot-tools-tag">
                        {msg.tools.map((t) => (
                          <span key={t} className="tool-pill">
                            🔧 {t}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="copilot-text">{msg.content}</div>
                    <span className="copilot-time">{msg.timestamp}</span>
                  </div>
                </div>
              ))}

              {loading && (
                <div className="copilot-bubble-wrap ai-wrap">
                  <div className="copilot-msg-avatar">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
                    </svg>
                  </div>
                  <div className="copilot-bubble ai-bubble loading-bubble">
                    <div className="typing-dots">
                      <span /><span /><span />
                    </div>
                    <small>Đang tra cứu dữ liệu & xử lý...</small>
                  </div>
                </div>
              )}

              {error && (
                <div className="error-box" style={{ margin: "10px 0" }}>
                  <span>⚠️ {error}</span>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Footer Input Area */}
        <footer className="copilot-footer">
          <form
            className="copilot-input-form"
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
          >
            <textarea
              ref={textareaRef}
              rows={2}
              className="copilot-textarea"
              placeholder="Hỏi Copilot về chiến dịch, khách hàng, số dư..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
            />
            <button
              type="submit"
              className="btn primary copilot-send-btn"
              disabled={!input.trim() || loading}
              aria-label="Gửi câu hỏi"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m22 2-7 20-4-9-9-4Z" />
                <path d="M22 2 11 13" />
              </svg>
            </button>
          </form>

          <div className="copilot-security-footnote">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
            <span>STAFF_TOOLS được bảo vệ • Đã tự động lọc password, token & cookie</span>
          </div>
        </footer>
      </aside>
    </>
  );
}
