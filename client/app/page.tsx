"use client";

import { useState, useRef, useEffect } from "react";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Welcome to Agent Phone.\n\nThis is the mobile-first foundation. Ask me anything — next we wire real models, tools, and approval gates so you can sell this to individuals and organizations.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
    };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/v1/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thread_id: threadId,
          message: text,
        }),
      });

      if (!res.ok) throw new Error("API error");

      const data = await res.json();
      setThreadId(data.thread_id);

      setMessages((m) => [
        ...m,
        {
          id: data.message_id,
          role: "assistant",
          content: data.reply,
        },
      ]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content:
            "Could not reach the API. Make sure the backend is running and NEXT_PUBLIC_API_URL is correct.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-dvh max-w-lg mx-auto bg-gray-950">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-gray-800 safe-top">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-sm font-bold">
            A
          </div>
          <div>
            <h1 className="text-base font-semibold leading-tight">Agent Phone</h1>
            <p className="text-xs text-gray-400">Mobile AI workspace</p>
          </div>
        </div>
        <button className="text-xs text-gray-400 px-2 py-1 rounded border border-gray-700">
          Settings
        </button>
      </header>

      {/* Messages */}
      <main className="flex-1 chat-scroll px-3 py-4 space-y-3">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap ${
                msg.role === "user"
                  ? "bg-brand-600 text-white rounded-br-md"
                  : "bg-gray-800 text-gray-100 rounded-bl-md"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-800 rounded-2xl rounded-bl-md px-4 py-3 text-gray-400 text-sm">
              Thinking…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </main>

      {/* Input */}
      <footer className="border-t border-gray-800 px-3 py-3 safe-bottom">
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            rows={1}
            placeholder="Message your agent…"
            className="flex-1 resize-none bg-gray-900 border border-gray-700 rounded-2xl px-4 py-3 text-[15px] focus:outline-none focus:border-brand-500 max-h-32"
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            className="bg-brand-600 disabled:opacity-40 text-white rounded-full w-11 h-11 flex items-center justify-center font-medium"
          >
            ↑
          </button>
        </div>
      </footer>
    </div>
  );
}
