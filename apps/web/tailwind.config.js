/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
    './lib/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        adsos: {
          slate: '#16324f',
          slateHover: '#2a4a6e',
          border: '#e3e7ee',
          muted: '#66707d',
          ok: '#1e7d3c',
          warn: '#b7791f',
          bad: '#c0392b',
        },
      },
    },
  },
  plugins: [],
};
