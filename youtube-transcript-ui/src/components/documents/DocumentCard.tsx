import { Link } from 'react-router-dom';
import { FileText, Clock, ChevronRight, File, FileType2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { Document } from '@/api/types';
import { formatRelativeTime } from '@/utils/formatters';

interface DocumentCardProps {
  document: Document;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileTypeColor(fileType: string): string {
  switch (fileType.toLowerCase()) {
    case 'pdf':
      return 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-200 dark:border-red-800';
    case 'docx':
      return 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800';
    case 'txt':
      return 'bg-gray-500/10 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700';
    case 'md':
      return 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-200 dark:border-purple-800';
    default:
      return 'bg-muted text-muted-foreground';
  }
}

function getFileTypeIcon(fileType: string) {
  switch (fileType.toLowerCase()) {
    case 'pdf':
      return <FileType2 className="h-5 w-5" />;
    case 'md':
      return <FileText className="h-5 w-5" />;
    default:
      return <File className="h-5 w-5" />;
  }
}

export function DocumentCard({ document }: DocumentCardProps) {
  return (
    <div className="group flex flex-col rounded-xl border border-border bg-card p-4 shadow-sm hover:shadow-md hover:border-primary/30 transition-all animate-fade-in">
      {/* File Type Icon and Badge */}
      <div className="flex items-start justify-between mb-3">
        <div
          className={`flex h-10 w-10 items-center justify-center rounded-lg ${getFileTypeColor(
            document.file_type
          )}`}
        >
          {getFileTypeIcon(document.file_type)}
        </div>
        <Badge variant="outline" className={`uppercase text-xs ${getFileTypeColor(document.file_type)}`}>
          {document.file_type}
        </Badge>
      </div>

      {/* Filename */}
      <h3 className="font-medium text-card-foreground line-clamp-2 min-h-[2.5rem] mb-2">
        {document.original_filename}
      </h3>

      {/* File Info */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground mb-3">
        <span>{formatFileSize(document.file_size)}</span>
        {document.page_count && <span>{document.page_count} pages</span>}
        {document.word_count && <span>{document.word_count.toLocaleString()} words</span>}
      </div>

      {/* Timestamp */}
      <div className="flex items-center gap-1 text-xs text-muted-foreground mb-4">
        <Clock className="h-3 w-3" />
        <span>Uploaded {formatRelativeTime(document.created_at)}</span>
      </div>

      {/* Action */}
      <div className="mt-auto pt-2 border-t border-border">
        <Button variant="ghost" size="sm" className="w-full justify-between" asChild>
          <Link to={`/sessions?document=${document.id}`}>
            View in session
            <ChevronRight className="h-4 w-4" />
          </Link>
        </Button>
      </div>
    </div>
  );
}
