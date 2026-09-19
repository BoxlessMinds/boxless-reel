import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { MessagesSquare, Plus, Loader2, AlertCircle } from "lucide-react";
import { PageContainer } from "@/components/layout/PageContainer";
import { CrossChatSessionCard } from "@/components/cross-chat/CrossChatSessionCard";
import { SessionSelector } from "@/components/cross-chat/SessionSelector";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import {
  useCrossChatSessions,
  useCreateCrossChatSession,
  useDeleteCrossChatSession,
} from "@/hooks/useCrossChat";
import { ApiError } from "@/api/client";

export default function CrossChatPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const navigate = useNavigate();

  const { data, isLoading, error } = useCrossChatSessions();
  const createMutation = useCreateCrossChatSession();
  const deleteMutation = useDeleteCrossChatSession();

  const sessions = data?.items ?? [];

  const handleCreateSession = (sessionIds: string[]) => {
    createMutation.mutate(
      { sessionIds },
      {
        onSuccess: (newSession) => {
          setDialogOpen(false);
          toast.success("Cross-chat session created");
          navigate(`/cross-chat/${newSession.id}`);
        },
        onError: (error) => {
          if (error instanceof ApiError) {
            toast.error(error.message);
          } else {
            toast.error("Failed to create cross-chat session");
          }
        },
      }
    );
  };

  const handleDeleteSession = (id: string) => {
    deleteMutation.mutate(id, {
      onSuccess: () => {
        toast.success("Cross-chat session deleted");
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
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Cross-Chat</h1>
            <p className="text-muted-foreground mt-1">
              Query across multiple transcript sessions simultaneously
            </p>
          </div>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                New Cross-Chat
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>Select Sessions</DialogTitle>
              </DialogHeader>
              <SessionSelector
                onCreateSession={handleCreateSession}
                isLoading={createMutation.isPending}
              />
            </DialogContent>
          </Dialog>
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
            <span>Failed to load cross-chat sessions</span>
          </div>
        )}

        {/* Session List */}
        {!isLoading && !error && sessions.length > 0 && (
          <div className="space-y-3">
            {sessions.map((session) => (
              <CrossChatSessionCard
                key={session.id}
                session={session}
                onDelete={() => handleDeleteSession(session.id)}
              />
            ))}
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && sessions.length === 0 && (
          <EmptyState
            icon={MessagesSquare}
            title="No cross-chat sessions"
            description="Create a cross-chat to query across multiple transcript sessions at once."
            action={
              <Button onClick={() => setDialogOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                New Cross-Chat
              </Button>
            }
          />
        )}
      </div>
    </PageContainer>
  );
}
