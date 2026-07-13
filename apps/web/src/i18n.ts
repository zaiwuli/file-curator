export const messages = {
  en: {
    appName: 'File Curator',
    nav: { dashboard: 'Dashboard', sources: 'Sources', files: 'File browser', pipeline: 'Pipeline', review: 'Review center', preview: 'Virtual preview', execution: 'Execution', history: 'History', settings: 'Settings' },
    actions: { scan: 'Scan now', preview: 'Preview plan', execute: 'Execute plan', save: 'Save changes', back: 'Back' },
  },
  'zh-CN': {
    appName: 'File Curator',
    nav: { dashboard: '\u4eea\u8868\u76d8', sources: '\u6570\u636e\u6e90', files: '\u6587\u4ef6\u6d4f\u89c8\u5668', pipeline: '\u5904\u7406\u6d41\u7a0b', review: '\u5ba1\u6838\u4e2d\u5fc3', preview: '\u865a\u62df\u9884\u89c8', execution: '\u6267\u884c', history: '\u5386\u53f2\u8bb0\u5f55', settings: '\u8bbe\u7f6e' },
    actions: { scan: '\u7acb\u5373\u626b\u63cf', preview: '\u9884\u89c8\u8ba1\u5212', execute: '\u6267\u884c\u8ba1\u5212', save: '\u4fdd\u5b58\u66f4\u6539', back: '\u8fd4\u56de' },
  },
} as const

export type Locale = keyof typeof messages
