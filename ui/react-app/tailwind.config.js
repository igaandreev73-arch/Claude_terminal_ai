/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'bg-app':      '#0d0d0f',
        'bg-surface':  '#141418',
        'bg-elevated': '#1c1c22',
        'bg-input':    '#1e1e26',
        'bg-overlay':  '#16161d',
        accent: {
          blue:   '#3b82f6',
          green:  '#22d3a5',
          red:    '#f43f5e',
          orange: '#f59e0b',
          purple: '#a78bfa',
          teal:   '#14b8a6',
        },
        text: {
          primary:   '#f1f1f3',
          secondary: '#9898a8',
          muted:     '#55555f',
        },
      },
      fontFamily: {
        display: ['Space Grotesk', 'sans-serif'],
        body:    ['DM Sans', 'sans-serif'],
        mono:    ['JetBrains Mono', 'monospace'],
      },
      borderColor: {
        subtle:  'rgba(255,255,255,0.06)',
        default: 'rgba(255,255,255,0.10)',
        strong:  'rgba(255,255,255,0.18)',
      },
      animation: {
        'card-reveal': 'cardReveal 0.4s ease forwards',
        'live-pulse':  'livePulse 2s ease infinite',
        'shimmer':     'shimmer 1.5s linear infinite',
        'skeleton':    'skeletonPulse 1.5s ease infinite',
        'slide-in':    'eventSlideIn 0.2s ease forwards',
        'number-flash':'numberFlash 0.4s ease',
      },
      keyframes: {
        cardReveal: {
          from: { opacity: '0', transform: 'translateY(16px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        livePulse: {
          '0%':   { boxShadow: '0 0 0 0 rgba(34,211,165,0.6)' },
          '70%':  { boxShadow: '0 0 0 6px rgba(34,211,165,0)' },
          '100%': { boxShadow: '0 0 0 0 rgba(34,211,165,0)' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% center' },
          '100%': { backgroundPosition: '200% center' },
        },
        skeletonPulse: {
          '0%, 100%': { opacity: '0.4' },
          '50%':      { opacity: '0.8' },
        },
        eventSlideIn: {
          from: { opacity: '0', transform: 'translateX(-8px)' },
          to:   { opacity: '1', transform: 'translateX(0)' },
        },
        numberFlash: {
          '0%':   { opacity: '1' },
          '30%':  { opacity: '0.4' },
          '100%': { opacity: '1' },
        },
        donutDraw: {
          from: { strokeDashoffset: '440' },
          to:   { strokeDashoffset: 'var(--target-offset)' },
        },
      },
    },
  },
  plugins: [],
}
