import { create } from 'zustand';

interface Message {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
}

interface Session {
  id: string;
  title: string;
  system_prompt: string;
  created_at: string;
  updated_at: string;
}

interface ChatState {
  sessions: Session[];
  currentSessionId: string | null;
  messages: Message[];
  isLoading: boolean;
  streamingContent: string;
  streamingReasoning: string;

  setSessions: (sessions: Session[]) => void;
  setCurrentSessionId: (id: string | null) => void;
  setMessages: (messages: Message[]) => void;
  addMessage: (message: Message) => void;
  setLoading: (loading: boolean) => void;
  setStreamingContent: (content: string) => void;
  setStreamingReasoning: (content: string) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  sessions: [],
  currentSessionId: null,
  messages: [],
  isLoading: false,
  streamingContent: '',
  streamingReasoning: '',

  setSessions: (sessions) => set({ sessions }),
  setCurrentSessionId: (id) => set({ currentSessionId: id, messages: [], streamingContent: '', streamingReasoning: '' }),
  setMessages: (messages) => set({ messages }),
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  setLoading: (isLoading) => set({ isLoading }),
  setStreamingContent: (streamingContent) => set({ streamingContent }),
  setStreamingReasoning: (streamingReasoning) => set({ streamingReasoning }),
}));
