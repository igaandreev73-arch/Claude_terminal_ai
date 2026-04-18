interface Props {
  value: number
  decimals?: number
  suffix?: string
}

export function Badge({ value, decimals = 2, suffix = '%' }: Props) {
  const up = value >= 0
  return (
    <span className={up ? 'badge-up' : 'badge-down'}>
      {up ? '↑' : '↓'} {Math.abs(value).toFixed(decimals)}{suffix}
    </span>
  )
}
