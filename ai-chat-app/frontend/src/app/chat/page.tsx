"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { useChatStore } from "@/lib/store";
import {
  listSessions,
  createSession,
  deleteSession,
  getMessages,
  chatCompletions,
  clearToken,
} from "@/lib/api";
import { useRouter } from "next/navigation";

export default function ChatPage() {
  const {
    sessions,
    currentSessionId,
    messages,
    isLoading,
    streamingContent,
    streamingReasoning,
    setSessions,
    setCurrentSessionId,
    setMessages,
    addMessage,
    setLoading,
    setStreamingContent,
    setStreamingReasoning,
  } = useChatStore();

  const [input, setInput] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    const t = localStorage.getItem("token");
    if (!t) {
      router.replace("/");
      return;
    }
    loadSessions();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent, streamingReasoning]);

  const loadSessions = async () => {
    try {
      const data = await listSessions();
      setSessions(data);
    } catch {}
  };

  const selectSession = async (id: string) => {
    setCurrentSessionId(id);
    try {
      const msgs = await getMessages(id);
      setMessages(msgs);
    } catch {}
  };

  const newChat = async () => {
    try {
      const session = await createSession();
      setSessions([session, ...sessions]);
      await selectSession(session.id);
    } catch {}
  };

  const removeSession = async (id: string) => {
    try {
      await deleteSession(id);
      setSessions(sessions.filter((s) => s.id !== id));
      if (currentSessionId === id) {
        setCurrentSessionId(null);
        setMessages([]);
      }
    } catch {}
  };

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;
    if (!currentSessionId) {
      await newChat();
      if (!useChatStore.getState().currentSessionId) return;
    }

    const sessionId = useChatStore.getState().currentSessionId!;
    const userMsg = input.trim();
    setInput("");

    addMessage({
      id: Date.now().toString(),
      session_id: sessionId,
      role: "user",
      content: userMsg,
      created_at: new Date().toISOString(),
    });

    setLoading(true);
    setStreamingContent("");
    setStreamingReasoning("");

    try {
      const res = await chatCompletions(sessionId, userMsg);
      if (!res.ok) {
        setStreamingContent(`错误: ${res.statusText}`);
        setLoading(false);
        return;
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        setLoading(false);
        return;
      }

      let fullContent = "";
      let fullReasoning = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value, { stream: true });
        const lines = text.split("\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6);
            if (data === "[DONE]") continue;
            try {
              const parsed = JSON.parse(data);
              if (parsed.content) {
                fullContent += parsed.content;
                setStreamingContent(fullContent);
              }
              if (parsed.reasoning) {
                fullReasoning += parsed.reasoning;
                setStreamingReasoning(fullReasoning);
              }
              if (parsed.error) {
                setStreamingContent(`错误: ${parsed.error}`);
              }
            } catch {}
          }
        }
      }

      if (fullContent) {
        addMessage({
          id: (Date.now() + 1).toString(),
          session_id: sessionId,
          role: "assistant",
          content: fullContent,
          created_at: new Date().toISOString(),
        });
      }
      setStreamingContent("");
      setStreamingReasoning("");
      loadSessions();
    } catch (err: any) {
      setStreamingContent(`错误: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleLogout = () => {
    clearToken();
    router.replace("/");
  };

  return (
    <div className="h-screen flex bg-gray-950">
      {/* Sidebar */}
      <div
        className={`${sidebarOpen ? "w-64" : "w-0"} transition-all duration-200 bg-gray-900 border-r border-gray-800 flex flex-col overflow-hidden`}
      >
        <div className="p-3 border-b border-gray-800">
          <button
            onClick={newChat}
            className="w-full py-2 px-3 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors"
          >
            + 新对话
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions.map((s) => (
            <div
              key={s.id}
              onClick={() => selectSession(s.id)}
              className={`group flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors ${
                currentSessionId === s.id
                  ? "bg-gray-700 text-white"
                  : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
              }`}
            >
              <span className="truncate flex-1">{s.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removeSession(s.id);
                }}
                className="opacity-0 group-hover:opacity-100 ml-2 text-gray-500 hover:text-red-400 transition-opacity"
              >
                &times;
              </button>
            </div>
          ))}
        </div>
        <div className="p-3 border-t border-gray-800 space-y-2">
          <button
            onClick={() => router.push("/settings")}
            className="w-full py-2 px-3 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-400 transition-colors"
          >
            设置
          </button>
          <button
            onClick={handleLogout}
            className="w-full py-2 px-3 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-400 transition-colors"
          >
            退出登录
          </button>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="h-12 flex items-center px-4 border-b border-gray-800 bg-gray-900/50">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="mr-3 text-gray-400 hover:text-white transition-colors"
          >
            {sidebarOpen ? "◀" : "▶"}
          </button>
          <span className="text-sm text-gray-400 truncate">
            {sessions.find((s) => s.id === currentSessionId)?.title || "AI Chat"}
          </span>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6">
          {!currentSessionId && messages.length === 0 ? (
            <div className="h-full flex items-center justify-center text-gray-500">
              <div className="text-center">
                <p className="text-lg mb-2">开始新对话</p>
                <p className="text-sm">点击左侧「+ 新对话」或直接输入消息</p>
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-6">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-blue-600 text-white"
                        : "bg-gray-800 text-gray-100"
                    }`}
                  >
                    {msg.role === "assistant" ? (
                      <div className="prose prose-invert prose-sm max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                          {msg.content}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    )}
                  </div>
                </div>
              ))}
              {/* Streaming message */}
              {(streamingContent || streamingReasoning) && (
                <div className="flex justify-start">
                  <div className="max-w-[80%] px-4 py-3 rounded-2xl bg-gray-800 text-gray-100 text-sm leading-relaxed">
                    {streamingReasoning && (
                      <details className="mb-2" open>
                        <summary className="text-xs text-gray-500 cursor-pointer mb-1">思考中...</summary>
                        <div className="text-xs text-gray-500 prose prose-invert prose-xs max-w-none overflow-hidden">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingReasoning}</ReactMarkdown>
                        </div>
                      </details>
                    )}
                    {streamingContent && (
                      <div className="prose prose-invert prose-sm max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                          {streamingContent}
                        </ReactMarkdown>
                      </div>
                    )}
                  </div>
                </div>
              )}
              {isLoading && !streamingContent && !streamingReasoning && (
                <div className="flex justify-start">
                  <div className="px-4 py-3 rounded-2xl bg-gray-800 text-gray-400 text-sm">
                    思考中...
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-gray-800 bg-gray-900/50 p-4">
          <div className="max-w-3xl mx-auto flex gap-3">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
              rows={1}
              className="flex-1 resize-none rounded-xl bg-gray-800 border border-gray-700 px-4 py-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={sendMessage}
              disabled={isLoading || !input.trim()}
              className="px-5 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:text-gray-500 rounded-xl text-sm font-medium transition-colors"
            >
              发送
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
