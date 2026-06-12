import { useState, useEffect, useRef } from 'react'

/**
 * Hook for incremental counting animation
 * @param {number} endValue - The final value to animate to
 * @param {number} duration - Animation duration in milliseconds (default 2000)
 * @param {boolean} isDecimal - Whether to preserve decimal precision (for percentages, etc.)
 * @returns {number} The current animated value
 */
export function useCountAnimation(endValue, duration = 2000, isDecimal = false) {
  const [displayValue, setDisplayValue] = useState(0)
  const animationIdRef = useRef(null)
  const startTimeRef = useRef(null)

  useEffect(() => {
    if (typeof endValue !== 'number' || endValue < 0) {
      setDisplayValue(0)
      return
    }

    const animate = (currentTime) => {
      if (!startTimeRef.current) {
        startTimeRef.current = currentTime
      }

      const elapsed = currentTime - startTimeRef.current
      const progress = Math.min(elapsed / duration, 1)
      
      // Easing function for smooth animation (cubic ease-out)
      const easeOut = 1 - Math.pow(1 - progress, 3)
      
      // Use floor for integers, keep decimals for percentages
      const currentValue = isDecimal 
        ? endValue * easeOut 
        : Math.floor(endValue * easeOut)
      
      setDisplayValue(currentValue)

      if (progress < 1) {
        animationIdRef.current = requestAnimationFrame(animate)
      }
    }

    startTimeRef.current = null
    animationIdRef.current = requestAnimationFrame(animate)

    return () => {
      if (animationIdRef.current) {
        cancelAnimationFrame(animationIdRef.current)
      }
    }
  }, [endValue, duration, isDecimal])

  return displayValue
}
