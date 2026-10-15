import { useState, useEffect, useRef } from 'react';

/**
 * AnimatedNumber - Animates a number from 0 to the target value on mount
 * @param {number} value - The target number to animate to
 * @param {function} formatter - Function to format the number (e.g., currency formatter)
 * @param {number} duration - Animation duration in milliseconds (default: 1000)
 * @param {string} privacyMask - Text to show when privacy mode is on (optional)
 */
export default function AnimatedNumber({ 
  value, 
  formatter = (n) => n.toLocaleString(), 
  duration = 1000,
  privacyMask = null,
  title, // shown on hover, e.g. the full amount behind a short "₹1.25 Crore"
}) {
  const [displayValue, setDisplayValue] = useState(0);
  const [hasAnimated, setHasAnimated] = useState(false);
  const startTimeRef = useRef(null);
  const animationFrameRef = useRef(null);
  const previousValueRef = useRef(0);

  useEffect(() => {
    // If privacy mask is provided, don't animate
    if (privacyMask) {
      return;
    }

    const targetValue = value || 0;

    // Respect the "reduce motion" accessibility setting: show the final value straight away
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setDisplayValue(targetValue);
      previousValueRef.current = targetValue;
      setHasAnimated(true);
      return;
    }

    const startValue = hasAnimated ? previousValueRef.current : 0;
    
    // Easing function for smooth animation
    const easeOutQuart = (t) => 1 - Math.pow(1 - t, 4);

    const animate = (timestamp) => {
      if (!startTimeRef.current) {
        startTimeRef.current = timestamp;
      }

      const elapsed = timestamp - startTimeRef.current;
      const progress = Math.min(elapsed / duration, 1);
      const easedProgress = easeOutQuart(progress);
      
      const currentValue = startValue + (targetValue - startValue) * easedProgress;
      setDisplayValue(currentValue);

      if (progress < 1) {
        animationFrameRef.current = requestAnimationFrame(animate);
      } else {
        setDisplayValue(targetValue);
        previousValueRef.current = targetValue;
        setHasAnimated(true);
      }
    };

    // Reset and start animation
    startTimeRef.current = null;
    animationFrameRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [value, duration, privacyMask]);

  // If privacy mask is provided, show it
  if (privacyMask) {
    return <>{privacyMask}</>;
  }

  return title ? <span title={title}>{formatter(displayValue)}</span> : <>{formatter(displayValue)}</>;
}
