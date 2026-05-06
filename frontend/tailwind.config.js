/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        accent: '#10a37f',
        'accent-hover': '#0d8f6e',
        sidebar: '#202123',
        'sidebar-hover': '#2a2b32',
      },
    },
  },
  plugins: [],
};
