import { useRef, useState } from 'react';
import { UploadCloud, FileJson, History, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
import { PageContainer } from '@/components/layout/PageContainer';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/EmptyState';
import { useWatchHistoryImports, useUploadWatchHistory } from '@/hooks/useWatchHistory';
import { formatDate } from '@/utils/formatters';
import { ApiError } from '@/api/client';
import type { WatchHistoryImport } from '@/api/types';

const ALLOWED_EXTENSION = '.json';
const MAX_SIZE = 50 * 1024 * 1024; // Takeout watch-history.json exports can be large

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function ImportRow({ item }: { item: WatchHistoryImport }) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
      <div className="flex items-center gap-2 min-w-0">
        <FileJson className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="truncate font-medium">{item.original_filename}</span>
      </div>
      <div className="flex shrink-0 items-center gap-4 text-xs text-muted-foreground">
        <span>{item.entry_count} entries</span>
        <span className="capitalize">{item.status}</span>
        <span>{formatDate(item.imported_at)}</span>
      </div>
    </div>
  );
}

export default function WatchHistoryImportPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const { data, isLoading, error } = useWatchHistoryImports({ skip: 0, limit: 20 });
  const uploadMutation = useUploadWatchHistory();

  const imports = data?.items ?? [];

  const validateFile = (file: File): string | null => {
    if (!file.name.toLowerCase().endsWith(ALLOWED_EXTENSION)) {
      return 'Please select a Takeout watch-history.json file';
    }
    if (file.size > MAX_SIZE) {
      return `File too large. Max size: ${formatFileSize(MAX_SIZE)}`;
    }
    return null;
  };

  const handleFile = (file: File) => {
    const validationError = validateFile(file);
    if (validationError) {
      toast.error(validationError);
      return;
    }
    setSelectedFile(file);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const handleImport = async () => {
    if (!selectedFile) return;
    try {
      const result = await uploadMutation.mutateAsync(selectedFile);
      toast.success(`Imported ${result.entry_count} entries from ${result.original_filename}`, {
        icon: <CheckCircle2 className="h-4 w-4" />,
      });
      setSelectedFile(null);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to import watch history');
    }
  };

  return (
    <PageContainer>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Watch History Imports</h1>
          <p className="text-muted-foreground mt-1">
            Import your Google Takeout watch history to purge already-watched videos from a playlist.
          </p>
        </div>

        <Card>
          <CardContent className="pt-6">
            <div
              className={`flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors ${
                isDragging ? 'border-primary bg-primary/5' : 'border-border'
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <UploadCloud className="h-8 w-8 text-muted-foreground" />
              {selectedFile ? (
                <div className="flex items-center gap-2 text-sm">
                  <FileJson className="h-4 w-4 text-muted-foreground" />
                  <span className="font-medium">{selectedFile.name}</span>
                  <span className="text-muted-foreground">({formatFileSize(selectedFile.size)})</span>
                </div>
              ) : (
                <div>
                  <p className="text-sm font-medium">Drag and drop your watch-history.json here</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Exported from Google Takeout &rsaquo; YouTube and YouTube Music &rsaquo; history
                  </p>
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept={ALLOWED_EXTENSION}
                className="hidden"
                onChange={handleFileSelect}
              />
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadMutation.isPending}
                >
                  Choose file
                </Button>
                <Button size="sm" onClick={handleImport} disabled={!selectedFile || uploadMutation.isPending}>
                  {uploadMutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Importing...
                    </>
                  ) : (
                    'Import'
                  )}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <div>
          <h2 className="text-lg font-semibold text-foreground mb-3">Past imports</h2>

          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          )}

          {error && (
            <div className="flex items-center justify-center gap-2 py-12 text-destructive">
              <AlertCircle className="h-5 w-5" />
              <span>Failed to load past imports</span>
            </div>
          )}

          {!isLoading && !error && imports.length > 0 && (
            <Card>
              <CardContent className="p-0">
                <div className="divide-y">
                  {imports.map((item) => (
                    <ImportRow key={item.id} item={item} />
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {!isLoading && !error && imports.length === 0 && (
            <EmptyState
              icon={History}
              title="No imports yet"
              description="Uploaded Takeout exports will appear here once imported."
            />
          )}
        </div>
      </div>
    </PageContainer>
  );
}
