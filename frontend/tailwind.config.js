/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#fff4ee',
          100: '#ffe4d0',
          200: '#ffc5a0',
          300: '#ff9d6a',
          400: '#ff7233',
          500: '#ff5900',
          600: '#e04e00',
          700: '#b83f00',
          800: '#8f3100',
          900: '#6b2500',
        },
        sidebar: '#0a0a0a',
      },
      fontFamily: {
        sans: ['Quicksand', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 3px 0 rgba(0,0,0,0.08), 0 4px 16px 0 rgba(0,0,0,0.06)',
        'card-hover': '0 4px 8px 0 rgba(0,0,0,0.10), 0 8px 24px 0 rgba(0,0,0,0.08)',
      },
    },
  },
  plugins: [],
}
