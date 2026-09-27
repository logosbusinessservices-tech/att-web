/** @type {import('tailwindcss').Config} */

// RVNL brand palette pulled from the logo:
//   charcoal #25201C · red #A01A16 · green #ADCA0D · beige page #f7f7f4
// We remap Tailwind's built-in color NAMES onto brand-aligned scales so the
// whole app rethemes without touching every className:
//   • slate  → warm charcoal/beige neutrals (headers, page bg, body text)
//   • emerald/green/sky/cyan/teal/lime → brand green family
//   • red/rose/indigo/violet/fuchsia   → brand red family (accents + alerts)
//   • amber/orange → olive-gold (caution, on-theme; never orange)
//   • blue → neutral (rare) so no stray blues leak in
const neutral = {
  50: '#eae6db', 100: '#e0dbce', 200: '#d3ccbb', 300: '#bcb4a0',
  400: '#9c927e', 500: '#75695b', 600: '#574f42', 700: '#403a31',
  800: '#2e2922', 900: '#25201c', 950: '#1a1613',
}
const green = {
  50: '#f6fae7', 100: '#eaf4c5', 200: '#dbeb95', 300: '#c8de55',
  400: '#adca0d', 500: '#96b00b', 600: '#7d9309', 700: '#5f7007',
  800: '#4b5807', 900: '#3e4808', 950: '#212706',
}
const red = {
  50: '#fbebea', 100: '#f6cfcd', 200: '#eaa19e', 300: '#dc716d',
  400: '#c94742', 500: '#a01a16', 600: '#8f1713', 700: '#771310',
  800: '#5d0f0d', 900: '#4b0d0b', 950: '#290605',
}
const gold = {
  50: '#f9f7ea', 100: '#f1edcb', 200: '#e3da9c', 300: '#d0c169',
  400: '#bda63f', 500: '#a08a22', 600: '#86731b', 700: '#6a5b16',
  800: '#524612', 900: '#43390f', 950: '#251f07',
}

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          charcoal: '#25201C',
          red: '#A01A16',
          'red-dark': '#571714',
          green: '#ADCA0D',
          beige: '#eae6db',
        },
        slate: neutral,
        gray: neutral,
        zinc: neutral,
        neutral,
        stone: neutral,
        emerald: green,
        green,
        lime: green,
        sky: green,
        cyan: green,
        teal: green,
        red,
        rose: red,
        indigo: red,
        violet: red,
        fuchsia: red,
        amber: gold,
        yellow: gold,
        orange: gold,
        blue: neutral,
      },
    },
  },
  plugins: [],
}
