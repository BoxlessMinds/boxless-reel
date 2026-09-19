import { useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { ChatInput } from "@/components/chat/ChatInput";
import { useCrossChatSession, useQueryCrossChatSession } from "@/hooks/useCrossChat";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import type { CrossChatSessionSummary } from "@/api/types";

export default function CrossChatDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { data: session, isLoading, error } = useCrossChatSession(id ?? "");
  const queryMutation = useQueryCrossChatSession();

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [session?.messages]);

  const handleSendMessage = (question: string) => {
    if (!id) return;
    queryMutation.mutate(
      { id, question },
      {
        onError: (error) => {
          if (error instanceof ApiError) {
            toast.error(error.message);
          } else {
            toast.error("Failed to send message");
          }
        },
      }
    );
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-muted-foreground">Cross-chat session not found</p>
        <Button variant="outline" onClick={() => navigate("/cross-chat")}>
          Back to Cross-Chat
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-border bg-card px-6 py-3">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/cross-chat")}
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-semibold text-foreground">Cross-Chat</h2>
            <div className="flex items-center gap-2 mt-1 overflow-x-auto pb-1">
              {session.referenced_sessions.map((ref: CrossChatSessionSummary) => (
                <div
                  key={ref.session_id}
                  className="flex items-center gap-2 flex-shrink-0 rounded-full bg-accent px-3 py-1"
                >
                  <div className="h-5 w-8 overflow-hidden rounded bg-muted">
                    <img
                      src={ref.thumbnail_url ?? "/placeholder.svg"}
                      alt={ref.video_title}
                      className="h-full w-full object-cover"
                    />
                  </div>
                  <span className="text-xs font-medium text-accent-foreground max-w-[150px] truncate">
                    {ref.video_title}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {session.messages.length === 0 && !queryMutation.isPending && (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            Ask a question to start querying across your selected sessions.
          </div>
        )}

        {session.messages.map((msg, index) => (
          <ChatMessage
            key={index}
            messageKey={index}
            role={msg.role}
            content={msg.content}
            citations={msg.citations}
          />
        ))}

        {queryMutation.isPending && (
          <div className="flex gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent flex-shrink-0">
              <Loader2 className="h-4 w-4 animate-spin text-accent-foreground" />
            </div>
            <div className="max-w-[80%] rounded-xl bg-card border border-border px-4 py-3">
              <p className="text-sm text-muted-foreground animate-pulse">
                Searching across {session.referenced_sessions.length} sessions...
              </p>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-border bg-card px-6 py-4">
        <ChatInput
          onSend={handleSendMessage}
          disabled={queryMutation.isPending}
          placeholder="Ask a question across all referenced sessions..."
        />
      </div>
    </div>
  );
}
