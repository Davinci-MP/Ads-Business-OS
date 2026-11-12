/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './app/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
    './lib/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        spotify: {
          base: '#121212',       // Pure content-first dark background
          surface: '#181818',    // Cards, panels, elevated surfaces
          hover: '#1f1f1f',      // Interactive, button & hover surfaces
          card: '#252525',       // Elevated card surface
          divider: '#282828',    // Subtle borders and dividers
          border: '#4d4d4d',     // Gray border on dark
          borderLight: '#7c7c7c',// Outlined button borders
          green: '#1ed760',      // Iconic Spotify Green for active states & primary CTAs
          greenHover: '#1db954', // Hover green
          white: '#ffffff',      // Pure white primary text
          silver: '#b3b3b3',     // Muted silver secondary text
          subtle: '#7c7c7c',     // Outlines & subtle labels
          red: '#f3727f',        // Semantic negative / die
          orange: '#ffa42b',     // Semantic warning / unsettled
          blue: '#539df5',       // Semantic announcement
        },
        adsos: {
          slate: 'var(--surface)',
          slateHover: 'var(--surface-2)',
          border: 'var(--line)',
          muted: 'var(--muted)',
          ok: 'var(--accent)',
          warn: 'var(--warning)',
          bad: 'var(--danger)',
        },
        brand: { emerald: '#10b981', indigo: '#6366f1' },
      },
      boxShadow: {
        'spotify-card': '0 8px 8px rgba(0, 0, 0, 0.3)',
        'spotify-modal': '0 8px 24px rgba(0, 0, 0, 0.5)',
        'spotify-elevated': '0 12px 32px rgba(0, 0, 0, 0.6)',
      },
      letterSpacing: {
        'spotify-pill': '1.4px',
        'spotify-wide': '2px',
      },
      borderRadius: {
        card: '12px',
        control: '8px',
        'spotify-card': '8px',
        'spotify-pill': '9999px',
      },
    },
  },
  plugins: [],
};
