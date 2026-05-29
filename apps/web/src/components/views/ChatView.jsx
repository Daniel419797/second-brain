"use client";

import { Bot, FileText, HelpCircle, Image as ImageIcon, Loader2, Mic, Plus, RotateCcw, Send, Terminal, Trash2, UserRound, Wrench, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024;
const MAX_ATTACHMENTS = 6;
const ATTACHMENT_ACCEPT = [
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
  "application/pdf",
  ".doc",
  ".docx",
  ".txt",
  ".md",
  ".csv",
  ".xls",
  ".xlsx",
  ".ppt",
  ".pptx"
].join(",");

export function ChatView({ messages, onSend, onClear, busy }) {
  const { api, data, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("chat") || {};
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState([]);
  const [mode, setMode] = useState("Normal");
  const [attachmentStatus, setAttachmentStatus] = useState("");
  const [uploading, setUploading] = useState(false);
  const attachmentsRef = useRef([]);
  const fileInputRef = useRef(null);
  const scrollRef = useRef(null);
  const messageCount = messages.length;
  const grouped = useMemo(() => groupMessages(messages), [messages]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ block: "end" });
  }, [messageCount, busy]);

  useEffect(() => {
    attachmentsRef.current = attachments;
  }, [attachments]);

  useEffect(() => () => {
    attachmentsRef.current.forEach((item) => {
      if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
    });
  }, []);

  async function submit(event) {
    event.preventDefault();
    const value = text.trim();
    if ((!value && !attachments.length) || busy || uploading) return;
    setAttachmentStatus("");
    setUploading(true);
    try {
      const uploaded = attachments.length ? await uploadAttachments(api, attachments) : [];
      setText("");
      clearAttachments();
      await onSend(applyChatMode(composeMessageWithAttachments(value, uploaded), mode));
    } catch (err) {
      setAttachmentStatus(err.message || "Could not upload attachment.");
    } finally {
      setUploading(false);
    }
  }

  async function quickAsk(value) {
    if (busy) return;
    await onSend(value);
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  function handleFilesSelected(event) {
    const selected = Array.from(event.target.files || []);
    event.target.value = "";
    if (!selected.length) return;
    const remainingSlots = MAX_ATTACHMENTS - attachments.length;
    const accepted = [];
    const rejected = [];

    for (const file of selected.slice(0, Math.max(0, remainingSlots))) {
      if (file.size > MAX_ATTACHMENT_BYTES) {
        rejected.push(`${file.name} is larger than 20MB`);
        continue;
      }
      if (!isAllowedAttachment(file)) {
        rejected.push(`${file.name} is not a supported file type`);
        continue;
      }
      accepted.push({
        id: cryptoRandom(),
        file,
        name: file.name,
        size: file.size,
        type: file.type,
        previewUrl: file.type.startsWith("image/") ? URL.createObjectURL(file) : ""
      });
    }

    if (selected.length > remainingSlots) {
      rejected.push(`Only ${MAX_ATTACHMENTS} attachments can be sent at once`);
    }
    if (accepted.length) {
      setAttachments((items) => [...items, ...accepted]);
    }
    setAttachmentStatus(rejected[0] || "");
  }

  function removeAttachment(id) {
    setAttachments((items) => {
      const target = items.find((item) => item.id === id);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return items.filter((item) => item.id !== id);
    });
  }

  function clearAttachments() {
    setAttachments((items) => {
      items.forEach((item) => {
        if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
      });
      return [];
    });
  }

  return (
    <section className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden bg-friday-bg text-white">
      <header className="flex min-h-[54px] items-center justify-between gap-3 border-b border-friday-line bg-[#0f141a] px-5">
        <div className="min-w-0">
          <h1 className="truncate text-[16px] font-extrabold leading-none">{copy?.title || "Friday Chat"}</h1>
          <p className="mt-1 truncate font-mono text-[11px] text-friday-muted">
            {copy?.subtitle || `Real orchestrator conversation / ${messageCount} message${messageCount === 1 ? "" : "s"} saved locally`}
          </p>
        </div>
        <button
          className="inline-flex min-h-8 shrink-0 items-center gap-2 border border-friday-line bg-[#151b22] px-3 font-mono text-[11px] text-[#dfe9f6] transition-colors hover:border-friday-accent disabled:opacity-50"
          type="button"
          onClick={onClear}
          disabled={!messageCount || busy}
        >
          <Trash2 size={14} />
          {copy?.empty?.messages ? "New Thread" : "New Chat"}
        </button>
      </header>

      <div className="friday-scroll min-h-0 overflow-y-auto overflow-x-hidden px-4 py-5">
        <div className="mx-auto grid max-w-[860px] gap-6">
          {!messages.length ? <EmptyConversation data={data} onQuickAsk={quickAsk} /> : null}
          {grouped.map((group) => (
            <section className="grid gap-4" key={group.day}>
              <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-4">
                <span className="h-px bg-friday-line" />
                <span className="font-mono text-[10px] uppercase tracking-[.16em] text-friday-muted">{group.day}</span>
                <span className="h-px bg-friday-line" />
              </div>
              {group.items.map((message, index) => <ChatMessage message={message} onQuickAsk={quickAsk} key={message.id || `${group.day}-${index}-${message.role}`} />)}
            </section>
          ))}
          {busy ? <ThinkingRow /> : null}
          <div ref={scrollRef} />
        </div>
      </div>

      <form className="border-t border-friday-line bg-[#0f141a] px-5 py-4" onSubmit={submit}>
        <div className="mx-auto max-w-[860px]">
          <div className="mb-3 flex min-w-0 flex-wrap items-center gap-2 text-[12px]">
            <span className="font-mono uppercase tracking-[.12em] text-white">Mode:</span>
            {["Normal", "Focused", "Teacher", "Debugger", "Silent Operator"].map((item, index) => (
              <button
                className={`min-h-7 border px-3 text-[12px] ${mode === item ? "border-[#45678c] bg-[#1a2a3d] text-friday-accent" : "border-transparent bg-transparent text-[#d8e2ee] hover:border-friday-line"}`}
                key={item}
                type="button"
                onClick={() => setMode(item)}
                aria-pressed={mode === item}
              >
                {item}
              </button>
            ))}
          </div>
          {attachments.length ? (
            <div className="mb-3 flex min-w-0 flex-wrap gap-2">
              {attachments.map((item) => (
                <AttachmentChip item={item} onRemove={() => removeAttachment(item.id)} key={item.id} />
              ))}
            </div>
          ) : null}

          <div className="grid min-h-[72px] grid-cols-[40px_minmax(0,1fr)_auto_auto] items-center gap-3 border border-friday-line bg-[#151b22] px-4">
            <input
              className="sr-only"
              ref={fileInputRef}
              type="file"
              multiple
              accept={ATTACHMENT_ACCEPT}
              onChange={handleFilesSelected}
            />
            <button
              className="grid h-10 w-10 place-items-center border border-friday-line bg-[#10161d] text-friday-accent transition-colors hover:border-friday-accent hover:bg-[#172334] disabled:cursor-not-allowed disabled:opacity-45"
              type="button"
              aria-label="Attach images or files"
              title="Attach images or files"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy || uploading || attachments.length >= MAX_ATTACHMENTS}
            >
              <Plus size={19} />
            </button>
            <textarea
              className="h-[48px] resize-none border-0 bg-transparent py-3 font-mono text-[14px] text-white outline-none placeholder:text-[#99a8bb]"
              value={text}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={handleKeyDown}
              maxLength={4000}
              rows={2}
              placeholder={copy?.labels?.ask || "Message Friday..."}
            />
            <Link
              className="grid h-10 w-10 place-items-center border border-transparent text-[#d8e4f2] transition-colors hover:border-friday-line hover:text-friday-accent"
              href="/voice-mode"
              aria-label="Open Voice Mode"
              title="Open Voice Mode"
            >
              <Mic size={18} />
            </Link>
            <button className="grid h-11 w-11 place-items-center border border-friday-blue bg-[#97c8f8] text-[#061420] transition-transform hover:scale-105 active:scale-95 disabled:opacity-50" type="submit" disabled={busy || uploading || (!text.trim() && !attachments.length)}>
              {uploading ? <Loader2 className="animate-spin" size={18} /> : <Send size={18} />}
            </button>
          </div>
          {attachmentStatus ? <p className="mt-2 text-[11px] text-[#ffbf7b]">{attachmentStatus}</p> : null}
          <p className="mt-2 text-[11px] text-friday-muted">Enter to send / Shift + Enter for newline</p>
        </div>
      </form>
    </section>
  );
}

function AttachmentChip({ item, onRemove }) {
  return (
    <div className="grid max-w-full grid-cols-[36px_minmax(0,1fr)_28px] items-center gap-2 border border-friday-line bg-[#151b22] px-2 py-2 text-[12px] text-[#dfe9f6]">
      <div className="grid h-9 w-9 place-items-center overflow-hidden border border-[#34475a] bg-[#10161d] text-friday-accent">
        {item.previewUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="h-full w-full object-cover" src={item.previewUrl} alt="" />
        ) : item.type?.startsWith("image/") ? (
          <ImageIcon size={16} />
        ) : (
          <FileText size={16} />
        )}
      </div>
      <div className="min-w-0">
        <p className="truncate font-mono text-[11px] text-white">{item.name}</p>
        <p className="mt-0.5 text-[10px] text-friday-muted">{formatBytes(item.size)}</p>
      </div>
      <button
        className="grid h-7 w-7 place-items-center border border-transparent text-friday-muted transition-colors hover:border-friday-line hover:text-white"
        type="button"
        aria-label={`Remove ${item.name}`}
        title={`Remove ${item.name}`}
        onClick={onRemove}
      >
        <X size={14} />
      </button>
    </div>
  );
}

async function uploadAttachments(api, attachments) {
  const uploaded = [];
  for (const item of attachments) {
    const dataUrl = await readFileAsDataUrl(item.file);
    uploaded.push(await api("/chat/attachments", {
      method: "POST",
      body: JSON.stringify({
        filename: item.name,
        content_type: item.type || "",
        data_url: dataUrl
      })
    }));
  }
  return uploaded;
}

function composeMessageWithAttachments(text, uploaded) {
  if (!uploaded.length) return text;
  const lines = uploaded.map((item) => {
    const size = formatBytes(item.size_bytes || 0);
    return `- ${item.filename} (${item.kind || "file"}, ${size}): ${item.path}`;
  });
  const attachmentBlock = `\n\nAttached files uploaded from chat:\n${lines.join("\n")}`;
  const intro = text || "Please review the attached file(s).";
  const maxIntroLength = Math.max(0, 3900 - attachmentBlock.length);
  return `${intro.slice(0, maxIntroLength)}${attachmentBlock}`;
}

function applyChatMode(text, mode) {
  if (!mode || mode === "Normal") return text;
  return `[Friday mode: ${mode}]\n${text || "Continue."}`;
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
    reader.readAsDataURL(file);
  });
}

function isAllowedAttachment(file) {
  if (file.type?.startsWith("image/") || file.type === "application/pdf") return true;
  const allowedExtensions = [".doc", ".docx", ".txt", ".md", ".csv", ".xls", ".xlsx", ".ppt", ".pptx"];
  const name = file.name.toLowerCase();
  return allowedExtensions.some((extension) => name.endsWith(extension));
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MB`;
}

function cryptoRandom() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function EmptyConversation({ data, onQuickAsk }) {
  const status = data.status?.running ? `${data.status.workers || 0} background worker(s) online` : "background workers stopped";
  const prompts = [
    "what are you doing?",
    "what tools do you have?",
    "generate an image of a cat",
    "what failed recently?"
  ];
  return (
    <div className="mx-auto mt-8 grid max-w-[680px] gap-5 border border-friday-line bg-[#151b22] p-5">
      <div className="flex items-center gap-2 font-mono text-[12px] uppercase tracking-[.12em] text-friday-accent">
        <Bot size={16} />
        Start a conversation
      </div>
      <div>
        <h2 className="text-[22px] font-extrabold leading-tight">Ask Friday anything, then keep the thread.</h2>
        <p className="mt-3 text-[13px] leading-relaxed text-[#d8e4f2]">
          Messages go through the real <Code>/chat</Code> orchestrator. This page now keeps a ChatGPT-style local history instead of only showing the latest reply.
        </p>
        <p className="mt-3 font-mono text-[12px] text-friday-muted">Current agent state: {status}</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {prompts.map((prompt) => (
          <button className="min-h-10 border border-friday-line bg-[#10161d] px-3 text-left text-[12px] text-[#dfe9f6] hover:border-friday-accent" type="button" onClick={() => onQuickAsk(prompt)} key={prompt}>
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

function ChatMessage({ message, onQuickAsk }) {
  const role = message.role === "user" ? "user" : message.role === "system" ? "system" : "friday";
  const isUser = role === "user";
  return (
    <article className={`grid min-w-0 gap-3 ${isUser ? "justify-items-end" : "grid-cols-[36px_minmax(0,1fr)]"}`}>
      {!isUser ? (
        <div className={`grid h-9 w-9 place-items-center border ${role === "system" ? "border-[#7a4a25] bg-[#22180f] text-[#ffbf7b]" : "border-[#526174] bg-[#17202a] text-friday-accent"}`}>
          <Bot size={17} />
        </div>
      ) : null}
      <div className={`min-w-0 ${isUser ? "max-w-[70%]" : "max-w-full"}`}>
        <div className={`mb-2 flex flex-wrap items-center gap-3 font-mono text-[11px] ${isUser ? "justify-end" : ""}`}>
          <span className={`inline-flex items-center gap-1 border px-2 py-1 ${isUser ? "border-[#45617c] bg-[#1a2835] text-[#eef6ff]" : "border-[#31587f] bg-[#132031] text-friday-accent"}`}>
            {isUser ? <UserRound size={13} /> : <Wrench size={13} />}
            {isUser ? "You" : role === "system" ? "System" : "Friday"}
          </span>
          <span className="text-friday-muted">{formatTime(message.timestamp)}</span>
        </div>
        <div className={`border px-5 py-4 text-[14px] leading-relaxed ${isUser ? "border-[#45617c] bg-[#1a2835] text-[#eef6ff]" : "border-friday-line bg-[#171d24] text-[#eef6ff]"}`}>
          <p className="m-0 whitespace-pre-wrap break-words">{message.text}</p>
        </div>
        {!isUser && role !== "system" ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <ActionButton icon={<HelpCircle size={14} />} label="Why did you say that?" onClick={() => onQuickAsk("why did you say that?")} />
            <ActionButton icon={<Terminal size={14} />} label="What tools do you have?" onClick={() => onQuickAsk("what tools do you have?")} />
            <ActionButton icon={<RotateCcw size={14} />} label="What failed recently?" onClick={() => onQuickAsk("what failed recently?")} />
          </div>
        ) : null}
      </div>
    </article>
  );
}

function ThinkingRow() {
  return (
    <div className="grid grid-cols-[36px_minmax(0,1fr)] gap-3">
      <div className="grid h-9 w-9 place-items-center border border-[#526174] bg-[#17202a] text-friday-accent">
        <Bot size={17} />
      </div>
      <div className="max-w-[220px] border border-friday-line bg-[#171d24] px-4 py-3 font-mono text-[12px] text-friday-muted">
        Friday is thinking...
      </div>
    </div>
  );
}

function groupMessages(messages) {
  return messages.reduce((groups, message) => {
    const day = formatDay(message.timestamp);
    const existing = groups.find((group) => group.day === day);
    if (existing) {
      existing.items.push(message);
    } else {
      groups.push({ day, items: [message] });
    }
    return groups;
  }, []);
}

function formatDay(value) {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return "Today";
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return "Today";
  return date.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

function formatTime(value) {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function Code({ children }) {
  return <code className="bg-[#2b313a] px-1.5 py-0.5 font-mono">{children}</code>;
}

function ActionButton({ icon, label, onClick }) {
  return (
    <button className="inline-flex min-h-8 items-center gap-1.5 border border-friday-line bg-[#151b22] px-3 text-[12px] text-white transition-colors hover:border-friday-accent" type="button" onClick={onClick}>
      {icon}
      {label}
    </button>
  );
}
