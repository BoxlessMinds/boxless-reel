import { Link } from "react-router-dom";
import { ArrowRight, Loader2, AlertCircle } from "lucide-react";
import { PageContainer } from "@/components/layout/PageContainer";
import { ExtractForm } from "@/components/transcript/ExtractForm";
import { TranscriptCard } from "@/components/transcript/TranscriptCard";
import { useTranscripts } from "@/hooks/useTranscripts";
import { formatDuration, formatDate } from "@/utils/formatters";

export default function HomePage() {
  const { data, isLoading, error } = useTranscripts({ page_size: 3 });
  const recentTranscripts = data?.items ?? [];

  return (
    <PageContainer>
      <div className="space-y-8">
        {/* Hero Section */}
        <div className="text-center py-8">
          <h1 className="text-3xl font-bold text-foreground mb-3">
            YouTube Transcript Extractor
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Extract, search, and interact with YouTube video transcripts.
            Get timestamped text and use AI to query video content.
          </p>
        </div>

        {/* Extract Form */}
        <ExtractForm />

        {/* Recent Transcripts */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-foreground">Recent Transcripts</h2>
            <Link
              to="/transcripts"
              className="flex items-center gap-1 text-sm font-medium text-primary hover:text-royal-600 transition-colors"
            >
              View All
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          )}

          {error && (
            <div className="flex items-center justify-center gap-2 py-12 text-destructive">
              <AlertCircle className="h-5 w-5" />
              <span>Failed to load transcripts</span>
            </div>
          )}

          {!isLoading && !error && recentTranscripts.length === 0 && (
            <div className="text-center py-12 text-muted-foreground">
              <p>No transcripts yet. Extract your first one above!</p>
            </div>
          )}

          {!isLoading && !error && recentTranscripts.length > 0 && (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {recentTranscripts.map((transcript) => (
                <TranscriptCard
                  key={transcript.id}
                  id={transcript.id}
                  videoId={transcript.video_id}
                  title={transcript.title}
                  channelName={transcript.channel_name ?? "Unknown"}
                  thumbnailUrl={transcript.thumbnail_url ?? "/placeholder.svg"}
                  duration={formatDuration(transcript.duration_seconds)}
                  language={transcript.language}
                  createdAt={formatDate(transcript.created_at)}
                  variant="grid"
                />
              ))}
            </div>
          )}
        </section>
      </div>
    </PageContainer>
  );
}
