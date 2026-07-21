'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowRight } from 'lucide-react'
import BrandMark from './BrandMark'

const LINKS = [
  { href: '#how', label: 'How it works' },
  { href: '#features', label: 'Features' },
  { href: '#pricing', label: 'Pricing' },
]

const APP = 'https://rocmporter-agent.vercel.app'

export default function Nav() {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <motion.header
      initial={{ y: -18, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: [0.22, 0.61, 0.36, 1] }}
      className="fixed inset-x-0 top-0 z-50 flex justify-center px-4 pt-4"
    >
      <nav
        aria-label="Main"
        className={[
          'edge-lit flex w-full max-w-6xl items-center gap-8 rounded-2xl px-5 py-3 transition-all duration-300',
          scrolled
            ? 'glass shadow-[0_18px_50px_-24px_rgba(0,0,0,0.9)]'
            : 'border border-transparent bg-transparent',
        ].join(' ')}
      >
        <a href="#top" className="flex items-center gap-2.5" aria-label="ROCmPorter home">
          <BrandMark size={30} />
          <span className="font-display text-[17px] font-bold tracking-[-0.02em]">ROCmPorter</span>
        </a>

        <ul className="ml-2 hidden items-center gap-7 md:flex">
          {LINKS.map((l) => (
            <li key={l.href}>
              <a className="nav-link" href={l.href}>
                {l.label}
              </a>
            </li>
          ))}
        </ul>

        <div className="ml-auto flex items-center gap-2.5">
          <a className="btn-ghost hidden !min-h-10 whitespace-nowrap !px-4 !py-2 text-sm sm:inline-flex" href={`${APP}/login`}>
            Sign in
          </a>
          <a className="btn-primary !min-h-10 whitespace-nowrap !px-4 !py-2 text-sm" href={`${APP}/app`}>
            <span className="hidden sm:inline">Start scanning</span>
            <span className="sm:hidden">Scan</span>
            <ArrowRight size={15} strokeWidth={2.4} aria-hidden />
          </a>
        </div>
      </nav>
    </motion.header>
  )
}
