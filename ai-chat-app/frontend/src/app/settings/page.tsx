"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { getAIConfig, updateAIConfig, getToken } from "@/lib/api";

export default function SettingsPage() {
  const [apiBaseUrl, setApiBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  useEffect(() => {
    const t = getToken();
    if (!t) {
      router.replace("/");
      return;
    }
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const config = await getAIConfig();
      setApiBaseUrl(config.api_base_url);
      setApiKey(config.api_key);
      setModel(config.model);
    } catch {}
  };

  const handleSave = async () => {
    setError("");
    setSaved(false);
    try {
      await updateAIConfig(apiBaseUrl, apiKey, model);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 p-8">
      <div className="max-w-xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-xl font-bold text-white">设置</h1>
          <button
            onClick={() => router.push("/chat")}
            className="text-sm text-gray-400 hover:text-white transition-colors"
          >
            返回聊天
          </button>
        </div>

        <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6 space-y-6">
          <h2 className="text-lg font-semibold text-white">AI 模型配置</h2>

          <div>
            <label className="block text-sm text-gray-400 mb-1">API 地址</label>
            <input
              type="text"
              value={apiBaseUrl}
              onChange={(e) => setApiBaseUrl(e.target.value)}
              className="w-full px-4 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="https://open.bigmodel.cn/api/paas/v4"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">API Key</label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="w-full px-4 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="输入 API Key"
            />
            <p className="mt-1 text-xs text-gray-500">
              含 **** 的为已保存的密钥，修改时请输入完整 Key
            </p>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">模型名称</label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full px-4 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="glm-4-flash"
            />
          </div>

          {error && (
            <div className="p-3 bg-red-900/50 border border-red-700 rounded-lg text-red-300 text-sm">
              {error}
            </div>
          )}

          {saved && (
            <div className="p-3 bg-green-900/50 border border-green-700 rounded-lg text-green-300 text-sm">
              保存成功
            </div>
          )}

          <button
            onClick={handleSave}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors"
          >
            保存配置
          </button>
        </div>

        <div className="mt-8 bg-gray-900 rounded-2xl border border-gray-800 p-6 space-y-4">
          <h2 className="text-lg font-semibold text-white">常用配置参考</h2>
          <div className="text-sm text-gray-400 space-y-3">
            <div>
              <p className="text-gray-300">智谱 GLM</p>
              <p>地址: https://open.bigmodel.cn/api/paas/v4</p>
              <p>模型: glm-4-flash / glm-4</p>
            </div>
            <div>
              <p className="text-gray-300">OpenAI / 兼容接口</p>
              <p>地址: https://api.openai.com/v1</p>
              <p>模型: gpt-4o / gpt-4o-mini</p>
            </div>
            <div>
              <p className="text-gray-300">Claude</p>
              <p>地址: https://api.anthropic.com/v1</p>
              <p>模型: claude-sonnet-4-20250514</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
