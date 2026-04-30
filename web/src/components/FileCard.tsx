import { FileText, FileType, File as FileIcon, X } from 'lucide-react'

interface FileCardProps {
  name?: string
  mediaType?: string
  url?: string
  onRemove?: () => void
  /** If true, show a remove button (for pending attachments) */
  removable?: boolean
  /** If true, clicking opens the file in a new tab (for persisted files) */
  clickable?: boolean
}

function getFileIcon(mediaType?: string) {
  if (!mediaType) return <FileIcon size={16} />

  if (mediaType.includes('pdf')) {
    return <FileType size={16} />
  }
  if (mediaType.includes('word') || mediaType.includes('document')) {
    return <FileType size={16} />
  }
  if (mediaType.includes('text')) {
    return <FileText size={16} />
  }

  return <FileIcon size={16} />
}

export function FileCard({
  name = 'File',
  mediaType,
  url,
  onRemove,
  removable,
  clickable,
}: FileCardProps) {
  // Truncate long filenames to ~20 chars
  const displayName = name.length > 20 ? `${name.substring(0, 17)}…` : name

  const handleClick = () => {
    if (clickable && url) {
      window.open(url, '_blank')
    }
  }

  return (
    <div className="group relative inline-block">
      <button
        onClick={handleClick}
        disabled={!clickable}
        className={`surface-raised flex items-center gap-2 rounded-lg border border-(--color-border) bg-(--color-surface) px-3 py-2 text-xs text-(--color-text) transition-all ${
          clickable ? 'cursor-pointer hover:border-(--color-accent) hover:bg-(--color-surface-2)' : ''
        }`}
        title={name}
      >
        <span className="flex-shrink-0 text-(--color-text-muted)">
          {getFileIcon(mediaType)}
        </span>
        <span className="flex-shrink-0 font-medium">{displayName}</span>
      </button>

      {removable && onRemove && (
        <button
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
          className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-(--color-surface-2) text-(--color-text-muted) ring-1 ring-(--color-border) shadow-sm transition-opacity opacity-100 hover:text-(--color-text) md:opacity-0 md:group-hover:opacity-100"
          aria-label="Remove file"
          title="Remove"
        >
          <X size={10} />
        </button>
      )}
    </div>
  )
}
