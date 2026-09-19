import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Link2, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { useExtractTranscript } from "@/hooks/useTranscripts";
import { ApiError } from "@/api/client";

export function ExtractForm() {
  const [url, setUrl] = useState("");
  const navigate = useNavigate();
  const extractMutation = useExtractTranscript();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!url.trim()) {
      toast.error("Please enter a YouTube URL");
      return;
    }

    // Basic URL validation
    const youtubeRegex = /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|embed\/|v\/|shorts\/)|youtu\.be\/)/;
    if (!youtubeRegex.test(url) && !url.match(/^[a-zA-Z0-9_-]{11}$/)) {
      toast.error("Please enter a valid YouTube URL or video ID");
      return;
    }

    extractMutation.mutate(
      { youtube_url: url },
      {
        onSuccess: (transcript) => {
          toast.success("Transcript extracted successfully!");
          setUrl("");
          navigate(`/transcripts/${transcript.id}`);
        },
        onError: (error) => {
          if (error instanceof ApiError) {
            if (error.status === 409) {
              toast.error("This video has already been extracted");
            } else if (error.status === 404) {
              toast.error("Video or transcript not available");
            } else if (error.status === 400) {
              toast.error("Invalid YouTube URL format");
            } else {
              toast.error(error.message);
            }
          } else {
            toast.error("Failed to extract transcript");
          }
        },
      }
    );
  };

  return (
    <div className="rounded-xl border border-border bg-card p-6 shadow-sm animate-fade-in">
      <div className="flex items-center gap-3 mb-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent">
          <Sparkles className="h-5 w-5 text-accent-foreground" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-card-foreground">Extract New Transcript</h2>
          <p className="text-sm text-muted-foreground">
            Paste a YouTube URL to extract its transcript
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-3">
        <div className="relative flex-1">
          <Link2 className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Paste YouTube URL here..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="pl-10"
            disabled={extractMutation.isPending}
          />
        </div>
        <Button type="submit" disabled={extractMutation.isPending}>
          {extractMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Extracting...
            </>
          ) : (
            "Extract"
          )}
        </Button>
      </form>

      <p className="mt-3 text-xs text-muted-foreground">
        Supports: youtube.com/watch?v=..., youtube.com/shorts/..., youtu.be/..., video IDs
      </p>
    </div>
  );
}
