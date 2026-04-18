import { useEffect, useRef, useState } from 'react'

interface Props {
  value: number
  format?: (v: number) => string
  className?: string
}

export function AnimatedNumber({ value, format, className }: Props) {
  const [flash, setFlash] = useState(false)
  const prev = useRef(value)

  useEffect(() => {
    if (prev.current !== value) {
      prev.current = value
      setFlash(true)
      const t = setTimeout(() => setFlash(false), 400)
      return () => clearTimeout(t)
    }
  }, [value])

  const display = format ? format(value) : value.toLocaleString()
  return (
    <span className={`${className ?? ''} ${flash ? 'price-flash' : ''}`}>
      {display}
    </span>
  )
}
