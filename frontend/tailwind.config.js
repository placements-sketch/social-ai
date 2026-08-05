/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      // Text was running small across the whole app: 435 uses of text-xs and
      // 189 of text-sm, at Tailwind's default 12px and 14px, are what most of
      // the interface is actually set in.
      //
      // Redefining the scale here rather than bumping the root font size,
      // because Tailwind's SPACING is also in rem — moving the root would
      // scale every padding, gap and fixed width with it and reflow layouts
      // that are already tuned. This changes type only.
      //
      // Line heights grow with it. Keeping text-xs on its default 1rem leading
      // at 13px would leave it tighter than it was at 12px, which reads as
      // cramped even though the letters got bigger.
      //
      // lg and above are untouched — headings and page titles were never the
      // complaint, and growing them too would push card titles onto two lines.
      fontSize: {
        xs:   ['0.8125rem', { lineHeight: '1.125rem' }],  // 13px, was 12
        sm:   ['0.9375rem', { lineHeight: '1.375rem' }],  // 15px, was 14
        base: ['1.0625rem', { lineHeight: '1.625rem' }],  // 17px, was 16
      },
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

