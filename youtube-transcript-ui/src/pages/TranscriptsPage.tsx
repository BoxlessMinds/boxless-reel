import { useState } from "react";
import { FileText, Loader2, AlertCircle, ChevronLeft, ChevronRight } from "lucide-react";
import { PageContainer } from "@/components/layout/PageContainer";
import { SearchBar } from "@/components/transcript/SearchBar";
import { TranscriptCard } from "@/components/transcript/TranscriptCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/button";
import { useTranscripts } from "@/hooks/useTranscripts";
import { useDebounce } from "@/hooks/useDebounce";
import { formatDuration, formatDate } from "@/utils/formatters";

export default function TranscriptsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [language, setLanguage] = useState("all");
  const [page, setPage] = useState(1);
  const debouncedSearch = useDebounce(searchQuery, 300);

  const { data, isLoading, error } = useTranscripts({
    search: debouncedSearch || undefined,
    language: language === "all" ? undefined : language,
    page,
    page_size: 20,
  });

  const transcripts = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  const total = data?.total ?? 0;

  // Reset to page 1 when search/filter changes
  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    setPage(1);
  };

  const handleLanguageChange = (value: string) => {
    setLanguage(value);
    setPage(1);
  };

  return (
    <PageContainer>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">All Transcripts</h1>
            <p className="text-muted-foreground mt-1">
              {total} transcript{total !== 1 ? "s" : ""} total
            </p>
          </div>
        </div>

        {/* Search & Filters */}
        <SearchBar
          searchQuery={searchQuery}
          onSearchChange={handleSearchChange}
          language={language}
          onLanguageChange={handleLanguageChange}
        />

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
            <span>Failed to load transcripts</span>
          </div>
        )}

        {/* Transcript List */}
        {!isLoading && !error && transcripts.length > 0 && (
          <>
            <div className="space-y-3">
              {transcripts.map((transcript) => (
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
                  variant="list"
                />
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-2 pt-4">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                >
                  <ChevronLeft className="h-4 w-4" />
                  Previous
                </Button>
                <span className="text-sm text-muted-foreground px-4">
                  Page {page} of {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                >
                  Next
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            )}
          </>
        )}

        {/* Empty State */}
        {!isLoading && !error && transcripts.length === 0 && (
          <EmptyState
            icon={FileText}
            title="No transcripts found"
            description={
              debouncedSearch || language !== "all"
                ? "Try adjusting your search or filters to find what you're looking for."
                : "Extract your first transcript from the home page."
            }
          />
        )}
      </div>
    </PageContainer>
  );
}
