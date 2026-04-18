interface Props {
  width?: string
  height?: string
  className?: string
}

export function Skeleton({ width = '100%', height = '16px', className }: Props) {
  return (
    <div
      className={`skeleton ${className ?? ''}`}
      style={{ width, height }}
    />
  )
}
