/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./*.{html,js}"],
  theme: {
      extend: {
          colors: {
              'bg-primary': '#0f0f10',
              'bg-secondary': '#1a1a1c',
              'bg-card': '#1a1a1c',
              'accent': '#5e6ad2',
              'accent-primary': '#5e6ad2',
              'text-primary': '#e1e1e3',
              'text-secondary': '#8a8a8e',
              'text-muted': '#6b7280',
              'border-color': '#2e2e32',
              // Playground colors
              'cosmic-bg': '#050509',
              'neon-blue': '#00f2ea',
              'neon-pink': '#ff00ff',
              'neon-yellow': '#faff00',
          },
          fontFamily: {
              sans: ['Inter', 'system-ui', 'sans-serif'],
              mono: ['JetBrains Mono', 'monospace'],
          },
          animation: {
              'pulse-fast': 'pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
              'float': 'float 3s ease-in-out infinite',
              'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
          },
          keyframes: {
              float: {
                  '0%, 100%': { transform: 'translateY(0)' },
                  '50%': { transform: 'translateY(-10px)' },
              }
          }
      }
  },
  plugins: [],
}

