"use client";

import {
  Bot,
  Check,
  Copy,
  FileText,
  Image as ImageIcon,
  Loader2,
  Mic,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  X
} from "lucide-react";
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

const CHAT_MODES = ["Normal", "Focused", "Teacher", "Debugger", "Silent Operator"];

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
    <section className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden bg-[#1f1f1f] text-[#ececec]">
      <header className="flex min-h-16 items-center justify-between gap-3 px-5 sm:px-7">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-[#3b3b3b] bg-[#262626] text-[#f3f3f3]">
            <Sparkles size={17} />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-[18px] font-semibold leading-tight tracking-[-0.01em]">{copy?.title || "Friday"}</h1>
            <p className="truncate text-[12px] text-[#a6a6a6]">{threadSubtitle(messageCount, data)}</p>
          </div>
        </div>
        <button
          className="inline-flex min-h-9 shrink-0 items-center gap-2 rounded-full border border-[#3b3b3b] bg-[#2b2b2b] px-3 text-[13px] font-medium text-[#ededed] transition-colors hover:bg-[#343434] disabled:opacity-40"
          type="button"
          onClick={onClear}
          disabled={!messageCount || busy}
        >
          <Trash2 size={15} />
          New chat
        </button>
      </header>

      <div className="friday-scroll min-h-0 overflow-y-auto overflow-x-hidden px-4 pb-5 pt-2">
        <div className="mx-auto grid min-h-full max-w-[960px] content-end gap-6">
          {!messages.length ? <EmptyConversation data={data} onQuickAsk={quickAsk} /> : null}
          {grouped.map((group) => (
            <section className="grid gap-7" key={group.day}>
              <div className="flex items-center justify-center">
                <span className="rounded-full bg-[#292929] px-3 py-1 text-[11px] font-medium text-[#9f9f9f]">{group.day}</span>
              </div>
              {group.items.map((message, index) => (
                <ChatMessage message={message} onQuickAsk={quickAsk} key={message.id || `${group.day}-${index}-${message.role}`} />
              ))}
            </section>
          ))}
          {busy ? <ThinkingRow /> : null}
          <div ref={scrollRef} />
        </div>
      </div>

      <form className="px-4 pb-4 sm:pb-5" onSubmit={submit}>
        <div className="mx-auto max-w-[960px]">
          {attachments.length ? (
            <div className="mb-2 flex min-w-0 flex-wrap gap-2 px-2">
              {attachments.map((item) => (
                <AttachmentChip item={item} onRemove={() => removeAttachment(item.id)} key={item.id} />
              ))}
            </div>
          ) : null}

          <div className="rounded-[28px] border border-[#474747] bg-[#2b2b2b] p-3 shadow-[0_16px_52px_rgba(0,0,0,0.28)]">
            <input
              className="sr-only"
              ref={fileInputRef}
              type="file"
              multiple
              accept={ATTACHMENT_ACCEPT}
              onChange={handleFilesSelected}
            />
            <textarea
              className="block max-h-[180px] min-h-[56px] w-full resize-none border-0 bg-transparent px-3 py-2 text-[16px] leading-relaxed text-[#f2f2f2] outline-none placeholder:text-[#9b9b9b]"
              value={text}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={handleKeyDown}
              maxLength={4000}
              rows={2}
              placeholder={copy?.labels?.ask || "Ask anything"}
            />
            <div className="flex min-w-0 items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <button
                  className="grid h-10 w-10 place-items-center rounded-full text-[#f1f1f1] transition-colors hover:bg-[#3a3a3a] disabled:cursor-not-allowed disabled:opacity-40"
                  type="button"
                  aria-label="Attach files"
                  title="Attach files"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={busy || uploading || attachments.length >= MAX_ATTACHMENTS}
                >
                  <Plus size={22} />
                </button>
                <ModePicker mode={mode} onChange={setMode} />
              </div>
              <div className="flex items-center gap-2">
                <Link
                  className="grid h-10 w-10 place-items-center rounded-full text-[#f1f1f1] transition-colors hover:bg-[#3a3a3a]"
                  href="/voice-mode"
                  aria-label="Open voice mode"
                  title="Open voice mode"
                >
                  <Mic size={19} />
                </Link>
                <button
                  className="grid h-11 w-11 place-items-center rounded-full bg-[#f4f4f4] text-[#161616] transition-transform hover:scale-[1.03] active:scale-95 disabled:bg-[#5a5a5a] disabled:text-[#9c9c9c]"
                  type="submit"
                  aria-label="Send message"
                  title="Send message"
                  disabled={busy || uploading || (!text.trim() && !attachments.length)}
                >
                  {uploading ? <Loader2 className="animate-spin" size={18} /> : <Send size={18} />}
                </button>
              </div>
            </div>
          </div>
          {attachmentStatus ? <p className="mt-2 px-3 text-[12px] text-[#ffbf7b]">{attachmentStatus}</p> : null}
        </div>
      </form>
    </section>
  );
}

function ModePicker({ mode, onChange }) {
  return (
    <label className="hidden min-h-9 items-center rounded-full bg-[#242424] px-3 text-[12px] font-medium text-[#d4d4d4] transition-colors hover:bg-[#323232] sm:inline-flex">
      <span className="sr-only">Conversation mode</span>
      <select
        className="max-w-[150px] appearance-none bg-transparent pr-2 text-current outline-none"
        value={mode}
        onChange={(event) => onChange(event.target.value)}
        aria-label="Conversation mode"
      >
        {CHAT_MODES.map((item) => (
          <option className="bg-[#242424] text-[#f4f4f4]" key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
    </label>
  );
}

function AttachmentChip({ item, onRemove }) {
  return (
    <div className="grid max-w-full grid-cols-[36px_minmax(0,1fr)_28px] items-center gap-2 rounded-[16px] border border-[#454545] bg-[#2b2b2b] px-2 py-2 text-[12px] text-[#ececec]">
      <div className="grid h-9 w-9 place-items-center overflow-hidden rounded-[12px] bg-[#1f1f1f] text-[#dedede]">
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
        <p className="truncate text-[12px] font-medium text-[#f1f1f1]">{item.name}</p>
        <p className="mt-0.5 text-[11px] text-[#9c9c9c]">{formatBytes(item.size)}</p>
      </div>
      <button
        className="grid h-7 w-7 place-items-center rounded-full text-[#a8a8a8] transition-colors hover:bg-[#3b3b3b] hover:text-white"
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
  const attachmentBlock = `\n\nAttached files:\n${lines.join("\n")}`;
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
  const status = data.status?.running ? "Friday is awake" : "Friday is standing by";
  const prompts = [
    "help me think through an idea",
    "what should I work on next?",
    "review what failed recently",
    "draft this into something cleaner"
  ];
  return (
    <div className="grid min-h-[56vh] content-center justify-items-center gap-8 py-10 text-center">
      <div className="grid justify-items-center gap-4">
        <div className="grid h-[52px] w-[52px] place-items-center rounded-full bg-[#2b2b2b] text-[#f1f1f1]">
          <Sparkles size={25} />
        </div>
        <div>
          <p className="mb-3 text-[13px] font-medium text-[#9f9f9f]">{status}</p>
          <h2 className="max-w-[760px] text-[clamp(32px,5vw,58px)] font-semibold leading-[1.05] tracking-[-0.02em] text-[#e8e1d7]">
            What shall we think through?
          </h2>
        </div>
      </div>
      <div className="flex max-w-[760px] flex-wrap justify-center gap-2">
        {prompts.map((prompt) => (
          <button
            className="min-h-10 rounded-full bg-[#303030] px-4 text-[14px] font-medium text-[#ececec] transition-colors hover:bg-[#3a3a3a]"
            type="button"
            onClick={() => onQuickAsk(prompt)}
            key={prompt}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

function ChatMessage({ message, onQuickAsk }) {
  const role = message.role === "user" ? "user" : message.role === "system" ? "system" : "friday";
  if (role === "system") {
    return <SystemMessage text={message.text} timestamp={message.timestamp} />;
  }
  return role === "user" ? <UserMessage message={message} /> : <AssistantMessage message={message} onQuickAsk={onQuickAsk} />;
}

function UserMessage({ message }) {
  return (
    <article className="flex justify-end">
      <div className="max-w-[74%] rounded-[24px] bg-[#303030] px-5 py-3 text-[15px] leading-relaxed text-[#f4f4f4] sm:max-w-[720px]">
        <p className="m-0 whitespace-pre-wrap break-words">{message.text}</p>
      </div>
    </article>
  );
}

function AssistantMessage({ message, onQuickAsk }) {
  return (
    <article className="grid max-w-[820px] grid-cols-[32px_minmax(0,1fr)] gap-4">
      <div className="mt-1 grid h-8 w-8 place-items-center rounded-full bg-[#2d2d2d] text-[#f1f1f1]">
        <Bot size={17} />
      </div>
      <div className="min-w-0">
        <div className="max-w-none text-[16px] leading-8 text-[#f2f2f2]">
          <p className="m-0 whitespace-pre-wrap break-words">{message.text}</p>
        </div>
        <div className="mt-3 flex items-center gap-1.5 text-[#9b9b9b]">
          <IconAction icon={<Copy size={17} />} label="Copy response" />
          <IconAction icon={<ThumbsUp size={17} />} label="Good response" />
          <IconAction icon={<ThumbsDown size={17} />} label="Bad response" />
          <IconAction icon={<RefreshCw size={17} />} label="Ask again" onClick={() => onQuickAsk("try that again, but make it more natural")} />
          <IconAction icon={<MoreHorizontal size={18} />} label="More actions" />
          <span className="ml-2 text-[12px] text-[#787878]">{formatTime(message.timestamp)}</span>
        </div>
      </div>
    </article>
  );
}

function SystemMessage({ text, timestamp }) {
  return (
    <article className="flex justify-center">
      <div className="inline-flex max-w-[760px] items-center gap-2 rounded-full bg-[#2c241b] px-3 py-1.5 text-[12px] text-[#f0c48d]">
        <Check size={14} />
        <span className="truncate">{text}</span>
        <span className="text-[#9c7850]">{formatTime(timestamp)}</span>
      </div>
    </article>
  );
}

function IconAction({ icon, label, onClick }) {
  return (
    <button
      className="grid h-8 w-8 place-items-center rounded-full transition-colors hover:bg-[#303030] hover:text-[#f2f2f2]"
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      {icon}
    </button>
  );
}

function ThinkingRow() {
  return (
    <div className="grid max-w-[820px] grid-cols-[32px_minmax(0,1fr)] gap-4">
      <div className="grid h-8 w-8 place-items-center rounded-full bg-[#2d2d2d] text-[#f1f1f1]">
        <Sparkles className="animate-spin" size={17} />
      </div>
      <div className="flex items-center gap-2 py-1 text-[14px] text-[#a8a8a8]">
        <span className="h-2 w-2 animate-pulse rounded-full bg-[#a8a8a8]" />
        Friday is thinking
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

function threadSubtitle(messageCount, data) {
  if (!messageCount) return "New conversation";
  const active = data.missions?.find((mission) => ["active", "running", "in_progress"].includes(String(mission.status || "").toLowerCase()));
  if (active?.title) return active.title;
  return `${messageCount} message${messageCount === 1 ? "" : "s"}`;
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
