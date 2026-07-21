/**
 * ROCmPorter mark — the tile's counter is cut away to form a chevron, so the
 * arrow is true negative space. Reads as a port, a migration arrow, and a
 * shell prompt at once.
 */
export default function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <defs>
        <linearGradient id="rp-mark" x1="2" y1="2" x2="30" y2="30" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FF365D" />
          <stop offset="0.45" stopColor="#FF365D" />
          <stop offset="1" stopColor="#7C5CFF" />
        </linearGradient>
      </defs>
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        fill="url(#rp-mark)"
        d="M8 2h16a6 6 0 0 1 6 6v16a6 6 0 0 1-6 6H8a6 6 0 0 1-6-6V8a6 6 0 0 1 6-6ZM11.4 9.6a1.6 1.6 0 0 0-1.13 2.73L14.94 17l-4.67 4.67a1.6 1.6 0 1 0 2.26 2.26l5.8-5.8a1.6 1.6 0 0 0 0-2.26l-5.8-5.8a1.6 1.6 0 0 0-1.13-.47ZM20.4 12.8a1.6 1.6 0 0 0 0 3.2h1.2a1.6 1.6 0 1 0 0-3.2h-1.2Z"
      />
    </svg>
  )
}
