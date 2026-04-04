import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'TAYA Odoo Docs',
  description: 'Tài liệu kỹ thuật dự án Odoo — Công ty TNHH Thực Phẩm TAYA Việt Nam',
  lang: 'vi-VN',
  base: '/',

  themeConfig: {
    siteTitle: 'TAYA Odoo Docs',

    nav: [
      { text: 'Trang chủ', link: '/' },
      { text: 'Migration', link: '/migration/' },
    ],

    sidebar: {
      '/migration/': [
        {
          text: 'Odoo Migration v15 → v19',
          items: [
            { text: 'Kinh nghiệm thực tế', link: '/migration/' },
            { text: 'Migration Pipeline', link: '/migration/pipeline' },
          ],
        },
      ],
    },

    search: {
      provider: 'local',
    },

    outline: {
      level: [2, 3],
      label: 'Mục lục',
    },

    docFooter: {
      prev: 'Trang trước',
      next: 'Trang sau',
    },
  },
})