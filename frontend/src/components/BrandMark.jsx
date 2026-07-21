/**
 * ROCmPorter brand mark.
 *
 * Concept — "the port", built on the Geometric + Negative Space styles:
 * a chip-shaped tile whose counter is cut away to form a right-pointing
 * chevron. The chevron is negative space, not a drawn shape, so the mark reads
 * three ways at once: a port/gateway, a migration arrow (CUDA → ROCm), and the
 * `>` of a shell prompt. The gradient runs AMD red → ROCm teal, which is the
 * migration itself.
 *
 * Vector only: one path set, no raster, themeable via `tone`, legible at 16px.
 */
export default function BrandMark({ size = 28, tone = 'brand', title }) {
  const gradientId = `rp-grad-${tone}`
  const fill = tone === 'mono' ? 'currentColor' : `url(#${gradientId})`

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role={title ? 'img' : 'presentation'}
      aria-hidden={title ? undefined : 'true'}
    >
      {title ? <title>{title}</title> : null}

      {tone !== 'mono' ? (
        <defs>
          <linearGradient id={gradientId} x1="2" y1="2" x2="30" y2="30" gradientUnits="userSpaceOnUse">
            <stop stopColor="#E31837" />
            <stop offset="0.3" stopColor="#E31837" />
            <stop offset="1" stopColor="#00C3B8" />
          </linearGradient>
        </defs>
      ) : null}

      {/* Tile with the chevron removed via even-odd, so the arrow is true
          negative space and inherits whatever sits behind the mark. */}
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        fill={fill}
        d="
          M8 2h16a6 6 0 0 1 6 6v16a6 6 0 0 1-6 6H8a6 6 0 0 1-6-6V8a6 6 0 0 1 6-6Z
          M11.4 9.6a1.6 1.6 0 0 0-1.13 2.73L14.94 17l-4.67 4.67a1.6 1.6 0 1 0 2.26 2.26l5.8-5.8a1.6 1.6 0 0 0 0-2.26l-5.8-5.8a1.6 1.6 0 0 0-1.13-.47Z
          M20.4 12.8a1.6 1.6 0 0 0 0 3.2h1.2a1.6 1.6 0 1 0 0-3.2h-1.2Z
        "
      />
    </svg>
  )
}
