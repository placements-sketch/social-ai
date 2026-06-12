import { useState, useEffect, useRef } from 'react'

/**
 * Premium smooth counting animation hook
 * @param {number} endValue - The final value to animate to
 * @param {number} duration - Animation duration in milliseconds (default 3000 for premium feel)
 * @param {boolean} isDecimal - Whether to preserve decimal precision (for percentages, etc.)
 * @returns {number} The current animated value
 */
export function useCountAnimation(endValue, duration = 3000, isDecimal = false) {
  const [displayValue, setDisplayValue] = useState(0)
  const animationIdRef = useRef(null)
  const startTimeRef = useRef(null)
  const previousValueRef = useRef(0)

  useEffect(() => {
    if (typeof endValue !== 'number' || endValue < 0) {
      setDisplayValue(0)
      return
    }

    // If value changed, update the reference
    if (endValue !== previousValueRef.current) {
      previousValueRef.current = endValue
    }

    const animate = (currentTime) => {
      if (!startTimeRef.current) {
        startTimeRef.current = currentTime
      }

      const elapsed = currentTime - startTimeRef.current
      const progress = Math.min(elapsed / duration, 1)
      
      // Premium easing: Cubic Bézier (0.34, 1.56, 0.64, 1) - smooth overshoot
      // This creates a subtle bounce effect for premium feel
      const easeOutCubic = 1 - Math.pow(1 - progress, 3)
      
      // Optional: Add a slight overshoot for more premium feel
      const overshootFactor = progress > 0.8 ? 1 + (1 - progress) * 0.1 : 1
      const smoothedProgress = Math.min(easeOutCubic * overshootFactor, 1)
      
      // Use floor for integers, keep decimals for percentages
      const currentValue = isDecimal 
        ? endValue * smoothedProgress 
        : Math.floor(endValue * smoothedProgress)
      
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
