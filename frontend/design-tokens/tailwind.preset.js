// Cenkor Tailwind preset — 共享给 admin-web / portal-web / 公网（website）
import { fontFamily } from 'tailwindcss/defaultTheme.js'

export default {
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', ...fontFamily.sans],
        display: ['"Plus Jakarta Sans"', ...fontFamily.sans],
        mono: ['"JetBrains Mono"', ...fontFamily.mono],
      },
      colors: {
        ink: {
          50:  'oklch(0.985 0.003 250)',
          100: 'oklch(0.97 0.003 260)',
          200: 'oklch(0.92 0.005 260)',
          300: 'oklch(0.83 0.005 260)',
          400: 'oklch(0.72 0.008 260)',
          500: 'oklch(0.62 0.008 260)',
          600: 'oklch(0.50 0.008 260)',
          700: 'oklch(0.40 0.008 260)',
          800: 'oklch(0.28 0.005 260)',
          900: 'oklch(0.18 0 0)',
        },
        accent: {
          DEFAULT: 'oklch(0.62 0.165 165)',
          dark:    'oklch(0.52 0.180 165)',
          light:   'oklch(0.92 0.060 165)',
          ink:     'oklch(0.32 0.140 165)',
        },
      },
      borderRadius: {
        '4xl': '2rem',
        '5xl': '2.5rem',
      },
      transitionTimingFunction: {
        'ease-out-quart': 'cubic-bezier(0.25, 1, 0.5, 1)',
        'ease-out-expo':  'cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
}
