import { useState, useEffect } from "react";
import { useParams, useNavigate, Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, Trash2, Copy, Globe, Clock, Calendar, Check, Loader2, AlertCircle, Bot, Settings, ExternalLink } from "lucide-react";
import { PageContainer } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { TranscriptViewer } from "@/components/transcript/TranscriptViewer";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { ChatInput } from "@/components/chat/ChatInput";
import { SessionDocuments } from "@/components/documents/SessionDocuments";
import { EmptyState } from "@/components/ui/EmptyState";
import { toast } from "sonner";
import { FileText, MessageSquare } from "lucide-react";
import { useTranscript, useDeleteTranscript } from "@/hooks/useTranscripts";
import { useCreateSession, useQuerySession, useSession } from "@/hooks/useSessions";
import { useUploadDocument } from "@/hooks/useDocuments";
import { useSettingsContext } from "@/contexts/SettingsContext";
import { formatDuration, formatDate } from "@/utils/formatters";
import { ApiError } from "@/api/client";
import type { Citation } from "@/api/types";

interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[] | null;
}

export default function TranscriptDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const resumeSessionId = searchParams.get('session');
  const defaultTab = searchParams.get('tab') || 'transcript';

  const [copied, setCopied] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [modelProvider, setModelProvider] = useState<"anthropic" | "openai">("anthropic");

  const { settings } = useSettingsContext();
  const { data: transcript, isLoading, error } = useTranscript(id!);
  const deleteMutation = useDeleteTranscript();
  const createSessionMutation = useCreateSession();
  const querySessionMutation = useQuerySession();
  const uploadDocumentMutation = useUploadDocument();

  // Fetch existing session data when resuming
  const { data: existingSession, isLoading: isLoadingSession } = useSession(resumeSessionId || '');

  // Initialize model provider from settings
  useEffect(() => {
    if (settings && !sessionId && !resumeSessionId) {
      setModelProvider(settings.default_provider);
    }
  }, [settings, sessionId, resumeSessionId]);

  // Initialize state from existing session when resuming
  useEffect(() => {
    if (existingSession && !sessionId) {
      setSessionId(existingSession.session_id);
      setModelProvider(existingSession.model_provider as "anthropic" | "openai");
      // Convert loaded messages to local format
      const loadedMessages: Message[] = existingSession.messages.map(msg => ({
        role: msg.role as "user" | "assistant",
        content: msg.content,
        citations: msg.citations,
      }));
      setMessages(loadedMessages);
    }
  }, [existingSession, sessionId]);

  // Check if chat is available (at least one provider configured)
  const chatAvailable = settings?.available_providers && settings.available_providers.length > 0;

  if (isLoading || (resumeSessionId && isLoadingSession)) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center py-24">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </PageContainer>
    );
  }

  if (error || !transcript) {
    return (
      <PageContainer>
        <EmptyState
          icon={FileText}
          title="Transcript not found"
          description="The transcript you're looking for doesn't exist or couldn't be loaded."
          action={
            <Button asChild>
              <Link to="/transcripts">Back to Transcripts</Link>
            </Button>
          }
        />
      </PageContainer>
    );
  }

  const handleCopyTranscript = () => {
    navigator.clipboard.writeText(transcript.transcript_text);
    setCopied(true);
    toast.success("Transcript copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDelete = () => {
    deleteMutation.mutate(id!, {
      onSuccess: () => {
        toast.success("Transcript deleted");
        navigate("/transcripts");
      },
      onError: (error) => {
        if (error instanceof ApiError) {
          toast.error(error.message);
        } else {
          toast.error("Failed to delete transcript");
        }
      },
    });
  };

  const handleSendMessage = async (message: string) => {
    if (isSending) return;
    setIsSending(true);

    // Add user message immediately
    const userMessage: Message = { role: "user", content: message };
    setMessages((prev) => [...prev, userMessage]);

    try {
      let currentSessionId = sessionId;

      // Create session if not exists
      if (!currentSessionId) {
        const session = await createSessionMutation.mutateAsync({
          transcriptId: id!,
          modelProvider,
        });
        currentSessionId = session.session_id;
        setSessionId(currentSessionId);
      }

      // Query the session
      const response = await querySessionMutation.mutateAsync({
        sessionId: currentSessionId,
        question: message,
      });

      // Add assistant response
      const assistantMessage: Message = {
        role: "assistant",
        content: response.content,
        citations: response.citations,
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      // Remove the user message on error
      setMessages((prev) => prev.slice(0, -1));

      if (error instanceof ApiError) {
        if (error.status === 503) {
          toast.error("AI features are temporarily unavailable");
        } else {
          toast.error(error.message);
        }
      } else {
        toast.error("Failed to send message");
      }
    } finally {
      setIsSending(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    // Validate file type
    const allowedExtensions = ['.pdf', '.docx', '.txt', '.md'];
    const ext = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
    if (!allowedExtensions.includes(ext)) {
      toast.error(`Invalid file type. Allowed: ${allowedExtensions.join(', ')}`);
      return;
    }

    // Validate file size
    const maxSize = ext === '.pdf' || ext === '.docx' ? 10 * 1024 * 1024 : 5 * 1024 * 1024;
    if (file.size > maxSize) {
      const maxSizeMB = maxSize / (1024 * 1024);
      toast.error(`File too large. Max size: ${maxSizeMB}MB`);
      return;
    }

    // If no session exists, create one first
    let currentSessionId = sessionId;
    if (!currentSessionId) {
      try {
        const session = await createSessionMutation.mutateAsync({
          transcriptId: id!,
          modelProvider,
        });
        currentSessionId = session.session_id;
        setSessionId(currentSessionId);
      } catch (error) {
        if (error instanceof ApiError) {
          toast.error(error.message);
        } else {
          toast.error("Failed to create session");
        }
        return;
      }
    }

    // Upload the file
    try {
      await uploadDocumentMutation.mutateAsync({ sessionId: currentSessionId, file });
      toast.success(`Uploaded ${file.name}`);
    } catch (error) {
      if (error instanceof ApiError) {
        toast.error(error.message);
      } else {
        toast.error("Failed to upload document");
      }
    }
  };

  return (
    <PageContainer>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <Button variant="ghost" onClick={() => navigate(-1)} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          <Button
            variant="ghost"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
            className="text-destructive hover:text-destructive hover:bg-destructive/10"
          >
            {deleteMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <Trash2 className="h-4 w-4 mr-2" />
            )}
            Delete
          </Button>
        </div>

        {/* Video Info */}
        <div className="flex flex-col md:flex-row gap-6 animate-fade-in">
          <div className="w-full md:w-72 flex-shrink-0">
            <div className="aspect-video rounded-xl overflow-hidden bg-muted">
              <img
                src={transcript.thumbnail_url ?? "/placeholder.svg"}
                alt={transcript.title}
                className="h-full w-full object-cover"
              />
            </div>
          </div>
          <div className="flex-1">
            <h1 className="text-2xl font-bold text-foreground mb-3">
              {transcript.title}
            </h1>
            <p className="text-lg text-muted-foreground mb-4">
              {transcript.channel_name ?? "Unknown Channel"}
            </p>
            <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <Clock className="h-4 w-4" />
                {formatDuration(transcript.duration_seconds)}
              </span>
              <span className="flex items-center gap-1.5">
                <Globe className="h-4 w-4" />
                {transcript.language}
              </span>
              <span className="flex items-center gap-1.5">
                <Calendar className="h-4 w-4" />
                {formatDate(transcript.created_at)}
              </span>
            </div>
            <a
              href={`https://www.youtube.com/watch?v=${transcript.video_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-4 inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              <ExternalLink className="h-4 w-4" />
              Watch on YouTube
            </a>
          </div>
        </div>

        {/* Tabs */}
        <Tabs defaultValue={defaultTab} className="w-full">
          <TabsList className="w-full max-w-xs">
            <TabsTrigger value="transcript" className="flex-1 gap-2">
              <FileText className="h-4 w-4" />
              Transcript
            </TabsTrigger>
            <TabsTrigger value="chat" className="flex-1 gap-2">
              <MessageSquare className="h-4 w-4" />
              Chat
            </TabsTrigger>
          </TabsList>

          <TabsContent value="transcript" className="mt-6">
            <TranscriptViewer segments={transcript.transcript_segments} />
            <Button
              onClick={handleCopyTranscript}
              variant="outline"
              className="mt-4 w-full"
            >
              {copied ? (
                <>
                  <Check className="h-4 w-4 mr-2" />
                  Copied!
                </>
              ) : (
                <>
                  <Copy className="h-4 w-4 mr-2" />
                  Copy Full Transcript
                </>
              )}
            </Button>
          </TabsContent>

          <TabsContent value="chat" className="mt-6">
            {!chatAvailable ? (
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>No API Keys Configured</AlertTitle>
                <AlertDescription className="flex items-center justify-between">
                  <span>Configure API keys to enable chat features.</span>
                  <Button asChild variant="outline" size="sm">
                    <Link to="/settings" className="gap-2">
                      <Settings className="h-4 w-4" />
                      Settings
                    </Link>
                  </Button>
                </AlertDescription>
              </Alert>
            ) : (
              <div className="rounded-xl border border-border bg-card">
                {/* Model Selector */}
                <div className="flex items-center justify-between border-b border-border p-3">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Bot className="h-4 w-4" />
                    <span>Model Provider</span>
                  </div>
                  <Select
                    value={modelProvider}
                    onValueChange={(value: "anthropic" | "openai") => setModelProvider(value)}
                    disabled={sessionId !== null}
                  >
                    <SelectTrigger className="w-[160px] h-8">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {settings?.available_providers.includes("anthropic") && (
                        <SelectItem value="anthropic">Anthropic</SelectItem>
                      )}
                      {settings?.available_providers.includes("openai") && (
                        <SelectItem value="openai">OpenAI</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                </div>

                {/* Session Documents */}
                <SessionDocuments sessionId={sessionId} />

                {/* Chat Messages */}
                <div className="h-[50vh] lg:h-[360px] overflow-y-auto p-4 space-y-4 scrollbar-thin">
                  {messages.length === 0 ? (
                    <div className="h-full flex items-center justify-center">
                      <div className="text-center">
                        <MessageSquare className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" />
                        <p className="text-muted-foreground">
                          Ask a question about this transcript
                        </p>
                        <p className="text-xs text-muted-foreground/60 mt-1">
                          Model: {modelProvider === "anthropic" ? "Claude" : "GPT-4"}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <>
                      {messages.map((message, index) => (
                        <ChatMessage
                          key={index}
                          messageKey={index}
                          role={message.role}
                          content={message.content}
                          citations={message.citations}
                        />
                      ))}
                      {isSending && (
                        <div className="flex gap-3">
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent flex-shrink-0">
                            <Loader2 className="h-4 w-4 animate-spin text-accent-foreground" />
                          </div>
                          <div className="bg-card border border-border rounded-xl px-4 py-3">
                            <p className="text-sm text-muted-foreground">Thinking...</p>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>

                {/* Chat Input */}
                <div className="border-t border-border p-4">
                  <ChatInput
                    onSend={handleSendMessage}
                    onFileSelect={handleFileUpload}
                    disabled={isSending}
                    showFileUpload={true}
                  />
                </div>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </PageContainer>
  );
}
