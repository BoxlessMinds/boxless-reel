import { useRef, useState } from 'react';
import { FileText, Plus, X, Loader2, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { toast } from 'sonner';
import { useSessionDocuments, useUploadDocument, useDeleteDocument } from '@/hooks/useDocuments';
import { ApiError } from '@/api/client';

// Allowed file types
const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md'];
const ALLOWED_MIME_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/markdown',
];

// Max file sizes (in bytes)
const MAX_SIZE_PDF_DOCX = 10 * 1024 * 1024; // 10MB
const MAX_SIZE_TXT_MD = 5 * 1024 * 1024; // 5MB

interface SessionDocumentsProps {
  sessionId: string | null;
  onSessionRequired?: () => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileExtension(filename: string): string {
  const ext = filename.toLowerCase().slice(filename.lastIndexOf('.'));
  return ext;
}

function getFileTypeIcon(fileType: string): string {
  switch (fileType.toLowerCase()) {
    case 'pdf':
      return '📄';
    case 'docx':
      return '📝';
    case 'txt':
      return '📃';
    case 'md':
      return '📋';
    default:
      return '📁';
  }
}

export function SessionDocuments({ sessionId, onSessionRequired }: SessionDocumentsProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const { data: documentsData, isLoading, error } = useSessionDocuments(sessionId);
  const uploadMutation = useUploadDocument();
  const deleteMutation = useDeleteDocument();

  const documents = documentsData?.documents ?? [];
  const maxDocuments = documentsData?.max_documents ?? 5;
  const canAddMore = documentsData?.can_add_more ?? true;

  const validateFile = (file: File): string | null => {
    // Check file extension
    const ext = getFileExtension(file.name);
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Invalid file type. Allowed: ${ALLOWED_EXTENSIONS.join(', ')}`;
    }

    // Check MIME type
    if (!ALLOWED_MIME_TYPES.includes(file.type) && file.type !== '') {
      // Some browsers don't set MIME type for .md files
      if (ext !== '.md') {
        return `Invalid file type: ${file.type}`;
      }
    }

    // Check file size
    const maxSize = ext === '.pdf' || ext === '.docx' ? MAX_SIZE_PDF_DOCX : MAX_SIZE_TXT_MD;
    if (file.size > maxSize) {
      return `File too large. Max size: ${formatFileSize(maxSize)}`;
    }

    return null;
  };

  const handleUpload = async (file: File) => {
    if (!sessionId) {
      onSessionRequired?.();
      toast.error('Start a conversation first to attach documents');
      return;
    }

    const validationError = validateFile(file);
    if (validationError) {
      toast.error(validationError);
      return;
    }

    if (!canAddMore) {
      toast.error(`Maximum ${maxDocuments} documents allowed per session`);
      return;
    }

    try {
      await uploadMutation.mutateAsync({ sessionId, file });
      toast.success(`Uploaded ${file.name}`);
    } catch (error) {
      if (error instanceof ApiError) {
        toast.error(error.message);
      } else {
        toast.error('Failed to upload document');
      }
    }
  };

  const handleDelete = async (documentId: string, filename: string) => {
    if (!sessionId) return;

    try {
      await deleteMutation.mutateAsync({ sessionId, documentId });
      toast.success(`Removed ${filename}`);
    } catch (error) {
      if (error instanceof ApiError) {
        toast.error(error.message);
      } else {
        toast.error('Failed to remove document');
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleUpload(file);
    }
    // Reset input so same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
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
    if (file) {
      handleUpload(file);
    }
  };

  // Don't render if no session yet - show placeholder
  if (!sessionId) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground border-b border-border">
        <FileText className="h-3.5 w-3.5" />
        <span>Send a message to attach documents</span>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        <span className="text-xs text-muted-foreground">Loading documents...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 text-xs text-destructive border-b border-border">
        <AlertCircle className="h-3.5 w-3.5" />
        <span>Failed to load documents</span>
      </div>
    );
  }

  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 border-b border-border transition-colors ${
        isDragging ? 'bg-primary/5 border-primary/30' : ''
      }`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />

      {/* Document badges */}
      <div className="flex items-center gap-1.5 flex-wrap flex-1 min-w-0">
        {documents.map((doc) => (
          <TooltipProvider key={doc.id} delayDuration={0}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge
                  variant="secondary"
                  className="flex items-center gap-1 pr-1 max-w-[150px] cursor-default"
                >
                  <span className="text-xs">{getFileTypeIcon(doc.file_type)}</span>
                  <span className="truncate text-xs">{doc.original_filename}</span>
                  <button
                    onClick={() => handleDelete(doc.id, doc.original_filename)}
                    disabled={deleteMutation.isPending}
                    className="ml-0.5 p-0.5 rounded hover:bg-destructive/20 hover:text-destructive transition-colors disabled:opacity-50"
                    aria-label={`Remove ${doc.original_filename}`}
                  >
                    {deleteMutation.isPending ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <X className="h-3 w-3" />
                    )}
                  </button>
                </Badge>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="text-xs">
                <p className="font-medium">{doc.original_filename}</p>
                <p className="text-muted-foreground">
                  {formatFileSize(doc.file_size)}
                  {doc.page_count && ` • ${doc.page_count} pages`}
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ))}

        {/* Document count and add button */}
        {canAddMore && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept={ALLOWED_EXTENSIONS.join(',')}
              className="hidden"
              onChange={handleFileSelect}
            />
            <TooltipProvider delayDuration={0}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadMutation.isPending}
                    className="h-6 px-2 text-xs"
                  >
                    {uploadMutation.isPending ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Plus className="h-3 w-3" />
                    )}
                    <span className="sr-only md:not-sr-only">Add</span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="text-xs">
                  <p>Add document (PDF, DOCX, TXT, MD)</p>
                  <p className="text-muted-foreground">Max 10MB for PDF/DOCX, 5MB for TXT/MD</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </>
        )}
      </div>

      {/* Document count indicator */}
      <span className="text-xs text-muted-foreground flex-shrink-0">
        {documents.length}/{maxDocuments}
      </span>
    </div>
  );
}
