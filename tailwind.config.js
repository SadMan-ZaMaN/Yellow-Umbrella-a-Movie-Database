const defaultTheme = require('tailwindcss/defaultTheme');

/** @type {import('tailwindcss').Config} */
module.exports = {
  // classes are also built inside JS template strings, so scan scripts too
  content: ['./frontend/**/*.html', './frontend/statics/**/*.js'],
  theme: {
    extend: {
      colors: {
        brand: {
          dark: '#0B0C10',
          second: '#1f2833',
          gold: '#fbbf24',
          goldhover: '#f59e0b',
          red: '#d97706',
          gray: '#c5c6c7',
        },
      },
      fontFamily: {
        sans: ['Inter', ...defaultTheme.fontFamily.sans],
        inter: ['Inter', 'sans-serif'],
        outfit: ['Outfit', 'sans-serif'],
      },
    },
  },
};
