'use client'

import { motion } from 'framer-motion'
import type { ReactNode } from 'react'

/**
 * Scroll reveal.
 *
 * `immediate` plays on mount instead of on scroll — use it for anything above
 * the fold. Hero content that waits for a scroll event is content the visitor
 * may never see, and the primary CTA must never be one of those.
 */
export default function Reveal({
  children,
  delay = 0,
  y = 18,
  immediate = false,
  className,
}: {
  children: ReactNode
  delay?: number
  y?: number
  immediate?: boolean
  className?: string
}) {
  const transition = { duration: 0.5, delay, ease: [0.22, 0.61, 0.36, 1] as const }

  if (immediate) {
    return (
      <motion.div className={className} initial={{ opacity: 0, y }} animate={{ opacity: 1, y: 0 }} transition={transition}>
        {children}
      </motion.div>
    )
  }

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={transition}
    >
      {children}
    </motion.div>
  )
}
