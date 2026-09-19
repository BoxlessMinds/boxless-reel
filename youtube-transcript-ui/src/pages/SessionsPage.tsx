import { MessageSquare, Loader2, AlertCircle } from "lucide-react";
import { PageContainer } from "@/components/layout/PageContainer";
import { SessionCard } from "@/components/chat/SessionCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useSessions, useDeleteSession } from "@/hooks/useSessions";
import { formatRelativeTime } from "@/utils/formatters";
import { ApiError } from "@/api/client";

export default function SessionsPage() {
  const { data, isLoading, error } = useSessions();
  const deleteSessionMutation = useDeleteSession();

  const sessions = data?.items ?? [];

  const handleDeleteSession = (sessionId: string) => {
    deleteSessionMutation.mutate(sessionId, {
      onSuccess: () => {
        toast.success("Session deleted");
      },
      onError: (error) => {
        if (error instanceof ApiError) {
          toast.error(error.message);
        } else {
          toast.error("Failed to delete session");
        }
      },
    });
  };

  return (
    <PageContainer>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-foreground">Active Sessions</h1>
          <p className="text-muted-foreground mt-1">
            Continue your conversations with transcript AI
          </p>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="flex items-center justify-center gap-2 py-12 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load sessions</span>
          </div>
        )}

        {/* Session List */}
        {!isLoading && !error && sessions.length > 0 && (
          <div className="space-y-3">
            {sessions.map((session) => (
              <SessionCard
                key={session.session_id}
                id={session.session_id}
                videoTitle={session.video_title}
                thumbnailUrl={session.thumbnail_url ?? "/placeholder.svg"}
                queryCount={session.query_count}
                lastActivity={formatRelativeTime(session.last_activity)}
                transcriptId={session.transcript_id}
                onDelete={() => handleDeleteSession(session.session_id)}
              />
            ))}
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && sessions.length === 0 && (
          <EmptyState
            icon={MessageSquare}
            title="No active sessions"
            description="Start a chat with any transcript to create a session."
            action={
              <Button asChild>
                <Link to="/transcripts">Browse Transcripts</Link>
              </Button>
            }
          />
        )}
      </div>
    </PageContainer>
  );
}
