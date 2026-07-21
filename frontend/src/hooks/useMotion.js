import { useEffect, useRef } from 'react'

/**
 * Motion primitives, implemented with the Web Animations API / rAF instead of
 * GSAP so nothing is added to the bundle.
 *
 * Every hook is a no-op when the visitor prefers reduced motion, and every one
 * cleans up its listeners on unmount.
 */

function prefersReduced() {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  )
}

/**
 * Magnetic pull toward the cursor — the "complex" hover tier.
 *
 * Strength is clamped (default 0.28) so the element never leaves its own hit
 * box, which would break the click target. Deliberately reserved for one or two
 * focal elements per screen; applied broadly it reads as noise.
 */
export function useMagnetic(strength = 0.28, max = 10) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el || prefersReduced()) return undefined

    let raf = 0
    let currentX = 0
    let currentY = 0
    let targetX = 0
    let targetY = 0

    const clamp = (v) => Math.max(-max, Math.min(max, v))

    const loop = () => {
      // Critically damped-ish interpolation; cheap and frame-rate independent enough.
      currentX += (targetX - currentX) * 0.18
      currentY += (targetY - currentY) * 0.18
      el.style.transform = `translate3d(${currentX.toFixed(2)}px, ${currentY.toFixed(2)}px, 0)`
      if (Math.abs(targetX - currentX) > 0.05 || Math.abs(targetY - currentY) > 0.05) {
        raf = requestAnimationFrame(loop)
      } else {
        raf = 0
      }
    }

    const start = () => {
      if (!raf) raf = requestAnimationFrame(loop)
    }

    const apply = () => {
      el.style.transform = `translate3d(${currentX.toFixed(2)}px, ${currentY.toFixed(2)}px, 0)`
    }

    const onMove = (event) => {
      const rect = el.getBoundingClientRect()
      targetX = clamp((event.clientX - rect.left - rect.width / 2) * strength)
      targetY = clamp((event.clientY - rect.top - rect.height / 2) * strength)
      // rAF is suspended in background tabs, so nudge synchronously first: the
      // interaction still responds if the frame loop never gets to run.
      currentX += (targetX - currentX) * 0.35
      currentY += (targetY - currentY) * 0.35
      apply()
      start()
    }

    const onLeave = () => {
      targetX = 0
      targetY = 0
      start()
    }

    // Returning to a hidden tab must not leave the element stuck mid-pull.
    const onVisibility = () => {
      if (document.hidden) {
        targetX = 0
        targetY = 0
        currentX = 0
        currentY = 0
        apply()
      }
    }

    el.addEventListener('mousemove', onMove)
    el.addEventListener('mouseleave', onLeave)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      el.removeEventListener('mousemove', onMove)
      el.removeEventListener('mouseleave', onLeave)
      document.removeEventListener('visibilitychange', onVisibility)
      if (raf) cancelAnimationFrame(raf)
      el.style.transform = ''
    }
  }, [strength, max])

  return ref
}

/**
 * Staggered reveal for a container's children.
 * Caps the stagger at 8 children — past that the last items feel laggy.
 */
export function useStagger({ step = 70, y = 18, threshold = 0.2 } = {}) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return undefined

    const children = Array.from(el.children)
    if (!children.length) return undefined

    if (prefersReduced()) {
      children.forEach((child) => {
        child.style.opacity = ''
        child.style.transform = ''
      })
      return undefined
    }

    // Never let an animation be the only thing standing between a visitor and
    // the content. reveal() is idempotent and is called by the observer, by a
    // failsafe timer, and on unmount.
    let revealed = false
    const reveal = () => {
      if (revealed) return
      revealed = true
      children.forEach((child, i) => {
        const delay = Math.min(i, 8) * step
        child.animate(
          [
            { opacity: 0, transform: `translate3d(0, ${y}px, 0)` },
            { opacity: 1, transform: 'translate3d(0, 0, 0)' },
          ],
          { duration: 420, delay, easing: 'cubic-bezier(0.22,0.61,0.36,1)' },
        )
        // The element's own styles own the end state — the animation only plays
        // it in. Clearing these means a failed/interrupted animation can never
        // leave the content stuck invisible.
        child.style.opacity = ''
        child.style.transform = ''
        setTimeout(() => {
          child.style.willChange = ''
        }, delay + 460)
      })
    }

    children.forEach((child) => {
      child.style.opacity = '0'
      child.style.transform = `translate3d(0, ${y}px, 0)`
      child.style.willChange = 'transform, opacity'
    })

    if (typeof IntersectionObserver === 'undefined') {
      reveal()
      return undefined
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return
          observer.unobserve(entry.target)
          reveal()
        })
      },
      { threshold },
    )
    observer.observe(el)

    // Failsafe: whatever happens, this content becomes visible.
    const failsafe = setTimeout(reveal, 2500)

    return () => {
      observer.disconnect()
      clearTimeout(failsafe)
      reveal()
    }
  }, [step, y, threshold])

  return ref
}

/**
 * Animates a number from its previous value to the next one.
 * Returns a ref for the element whose textContent should be updated.
 */
export function useNumberFlow(value, { duration = 700 } = {}) {
  const ref = useRef(null)
  const previous = useRef(0)

  useEffect(() => {
    const el = ref.current
    if (!el) return undefined

    const from = previous.current
    const to = Number(value) || 0
    previous.current = to

    if (prefersReduced() || from === to) {
      el.textContent = String(to)
      return undefined
    }

    let raf = 0
    const start = performance.now()
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      el.textContent = String(Math.round(from + (to - from) * eased))
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, duration])

  return ref
}
