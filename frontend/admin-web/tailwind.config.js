/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts,tsx,js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
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
        },
      },
    },
  },
  plugins: [],
}
