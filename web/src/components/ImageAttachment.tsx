import { useState } from 'react'
import { X } from 'lucide-react'
import { ImageLightbox } from './ImageLightbox'

interface ImageAttachmentProps {
  src: string
  alt?: string
  onRemove?: () => void
  /** If true, show a remove button (for pending attachments) */
  removable?: boolean
  /**
   * If true, render the thumbnail at a compact size (160×160) suitable for
   * a horizontal preview strip next to an input bar. The full-size lightbox
   * preview on click is unchanged. Defaults to false (200×200).
   */
  compact?: boolean
}

export function ImageAttachment({ src, alt = 'Image', onRemove, removable, compact = false }: ImageAttachmentProps) {
  const [imageError, setImageError] = useState(false)
  const [lightboxOpen, setLightboxOpen] = useState(false)

  // Compact variant: used in the input-bar preview strip so tall images
  // don't dominate vertical space. The lightbox (on click) is unaffected.
  const sizeClass = compact
    ? 'max-h-[160px] max-w-[160px]'
    : 'max-h-[200px] max-w-[200px]'
  const errorSizeClass = compact ? 'h-[160px] w-[160px]' : 'h-[200px] w-[200px]'

  if (imageError) {
    return (
      <div className={`flex ${errorSizeClass} items-center justify-center rounded-lg border border-(--color-border) bg-(--color-surface) text-xs text-(--color-text-muted)`}>
        Failed to load image
      </div>
    )
  }

  return (
    <>
      <div className="group relative inline-block">
        <img
          src={src}
          alt={alt}
          onError={() => setImageError(true)}
          onClick={() => setLightboxOpen(true)}
          className={`${sizeClass} cursor-pointer rounded-lg border border-(--color-border) object-cover shadow-sm`}
        />
        {removable && onRemove && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onRemove()
            }}
            className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-(--color-surface-2) text-(--color-text-muted) ring-1 ring-(--color-border) shadow-sm transition-opacity opacity-100 hover:text-(--color-text) md:opacity-0 md:group-hover:opacity-100"
            aria-label="Remove image"
            title="Remove"
          >
            <X size={10} />
          </button>
        )}
      </div>

      <ImageLightbox
        src={src}
        alt={alt}
        isOpen={lightboxOpen}
        onClose={() => setLightboxOpen(false)}
      />
    </>
  )
}
