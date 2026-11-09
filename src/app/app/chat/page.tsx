import type { Metadata } from "next";
import { ChatWindow } from "@/components/chat/chat-window";

export const metadata: Metadata = {
  title: "AI Chat",
};

export default function ChatPage() {
  return <ChatWindow />;
}
