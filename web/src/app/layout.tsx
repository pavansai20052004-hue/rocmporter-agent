import type { Metadata } from 'next'
import { IBM_Plex_Sans, JetBrains_Mono, Sora } from 'next/font/google'
import './globals.css'

const sora = Sora({ subsets: ['latin'], weight: ['600', '700', '800'], variable: '--font-sora', display: 'swap' })
const plex = IBM_Plex_Sans({ subsets: ['latin'], weight: ['400', '500', '600'], variable: '--font-plex', display: 'swap' })
const mono = JetBrains_Mono({ subsets: ['latin'], weight: ['400', '500'], variable: '--font-jetbrains', display: 'swap' })

export const metadata: Metadata = {
  title: 'ROCmPorter — Break free from CUDA lock-in',
  description:
    'Scan any repository for CUDA lock-in, get an evidence-backed ROCm readiness score, and open a migration pull request — verified by hipcc in CI.',
  icons: { icon: '/favicon.svg' },
  openGraph: {
    title: 'ROCmPorter — Break free from CUDA lock-in',
    description: 'Evidence-backed CUDA → AMD ROCm migration, verified on the real ROCm toolchain.',
    type: 'website',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sora.variable} ${plex.variable} ${mono.variable}`}>
      <body className="antialiased">
        {/* Depth layers sit behind everything and never intercept pointer events. */}
        <div className="mesh" aria-hidden />
        <div className="grid-veil" aria-hidden />
        <div className="noise" aria-hidden />
        <div className="relative z-10">{children}</div>
      </body>
    </html>
  )
}
