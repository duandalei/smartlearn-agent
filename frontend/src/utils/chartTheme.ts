/**
 * ECharts 共用主题：墨线、朱砂点、纸面 tooltip。
 * 所有图表只从这里取色，避免各组件各写一套。
 */
export const CHART_COLORS = {
  ink: '#1c2a24',
  inkSoft: '#5e6b63',
  inkFaint: '#6e7a72',
  line: '#ddd8cb',
  lineStrong: '#c3bcab',
  grid: 'rgba(28, 42, 36, 0.08)',
  paper: '#fbfaf6',
  vermilion: '#b3402f',
  jade: '#4f7a5e',
  ochre: '#a97a2f',
  dust: '#6b7f8c',
} as const

export const CHART_FONT =
  "'Segoe UI', 'Microsoft YaHei', 'PingFang SC', sans-serif"

export const CHART_MONO = "'Cascadia Mono', Consolas, monospace"

/** 纸面 tooltip，带 1px 细线与极轻投影。 */
export const CHART_TOOLTIP = {
  backgroundColor: CHART_COLORS.paper,
  borderColor: CHART_COLORS.line,
  borderWidth: 1,
  padding: [8, 10] as [number, number],
  textStyle: {
    color: CHART_COLORS.ink,
    fontSize: 12,
    fontFamily: CHART_FONT,
  },
  extraCssText:
    'box-shadow: 0 8px 30px rgba(28, 42, 36, 0.12); border-radius: 2px;',
}
