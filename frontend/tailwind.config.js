/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Shop Zetu lime. 500 is the exact brand value (#99e600) so the
        // existing brand-500 usages land on-brand without being touched.
        brand: {
          50:  '#f8feeb',
          100: '#edfdce',
          200: '#dcfb9d',
          300: '#c9ff5c',
          400: '#b4ff1f',
          500: '#99e600',
          600: '#81c200',
          700: '#669900',
          800: '#527a00',
          900: '#416100',
        },
        sidebar: '#0a0a0a',
        // Dark surfaces, referenced by the theme layer in index.css.
        ink: {
          900: '#0a0a0a',  // page
          800: '#141414',  // cards / panels
          700: '#1c1c1c',  // raised (hover, inputs)
          600: '#262626',  // borders
          500: '#333333',  // strong borders
        },
      },
      fontFamily: {
        sans: ['Quicksand', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 3px 0 rgba(0,0,0,0.08), 0 4px 16px 0 rgba(0,0,0,0.06)',
        'card-hover': '0 4px 8px 0 rgba(0,0,0,0.10), 0 8px 24px 0 rgba(0,0,0,0.08)',
      },
      keyframes: {
        'pulse-live': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
      },
      animation: {
        'pulse-live': 'pulse-live 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}

