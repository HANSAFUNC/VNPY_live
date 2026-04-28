# 实验室 Tab 设计方案

> **日期:** 2026-04-29  
> **主题:** Web Dashboard V2 实验室 Tab

---

## 目标

在 Web Dashboard V2 中添加实验室 Tab，提供数据管理、信号管理和 K 线查看功能，支持信号收益分析。

---

## 布局设计（3列布局）

```
┌─────────────────────────────────────────────────────────────────┐
│  顶部工具栏: [项目选择器] [数据覆盖状态] [刷新按钮]               │
├──────────────┬──────────────────────────────┬───────────────────┤
│              │                              │                   │
│  左侧面板    │      中间面板                 │   右侧面板        │
│  导航菜单    │                              │                   │
│              │   K线图 / 信号详情            │   信号列表        │
│  - K线查看   │   (可切换视图)                │   - 信号日期      │
│  - 信号管理  │                              │   - 股票代码      │
│  - 数据管理  │                              │   - 信号类型      │
│              │                              │   - N天后收益     │
│              │                              │                   │
│              │                              │   [收益计算设置]  │
│              │                              │   N天后: [输入框] │
│              │                              │   [计算收益]      │
│              │                              │                   │
└──────────────┴──────────────────────────────┴───────────────────┘
```

---

## 功能模块

### 1. 数据管理

- 显示当前项目名称、数据源、指数
- 显示数据覆盖统计：
  - 总股票数
  - 日线/分钟线文件数
  - 数据日期范围
  - 最后更新时间
- 项目切换下拉框（支持切换数据源和指数）

### 2. 信号管理

- 信号列表展示：
  - 信号日期
  - 股票代码
  - 信号类型（买入/卖出）
  - 可点击查看详情
- 点击信号在 K 线图上标注信号点
- 删除信号按钮

### 3. K 线查看

- 股票搜索框（输入 vt_symbol）
- K 线图显示（使用 ECharts）
- 周期切换（1d/1m）
- 在 K 线上标注信号点（买入/卖出标记）

### 4. 信号收益分析

- 选择信号后，可以设置 N 天：
  - 输入框，范围 1-30 天
  - 或选择"到最新数据"
- 自动计算并显示：
  - 信号当天收盘价
  - N天后收盘价
  - 收益率（百分比）
  - 最大回撤（如果有足够数据）

---

## API 依赖

已实现的实验室 API：

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/lab/projects` | 获取项目列表 |
| POST | `/api/lab/project/switch` | 切换项目 |
| GET | `/api/lab/coverage` | 数据覆盖统计 |
| GET | `/api/lab/signals` | 信号列表 |
| GET | `/api/lab/signal/{name}` | 加载信号数据 |
| DELETE | `/api/lab/signal/{name}` | 删除信号 |
| GET | `/api/lab/kline/{vt_symbol}` | K 线数据 |

---

## 组件结构

```
web_dashboard_v2/src/
├── views/
│   └── LabView.vue              # 实验室 Tab 主视图
├── components/lab/
│   ├── ProjectSelector.vue      # 项目选择器
│   ├── DataCoverage.vue         # 数据覆盖统计
│   ├── SignalList.vue           # 信号列表
│   ├── SignalAnalyzer.vue       # 信号收益分析
│   └── KlineChart.vue           # K 线图组件
├── stores/
│   └── lab.ts                   # 实验室状态管理
└── api/
    └── lab.ts                   # 实验室 API 封装
```

---

## 状态管理

```typescript
interface LabState {
  // 项目信息
  currentProject: string;
  currentIndex: string;
  currentDataSource: string;
  
  // 数据覆盖
  coverage: DataCoverage | null;
  
  // 信号
  signals: Signal[];
  selectedSignal: Signal | null;
  
  // K线
  selectedStock: string;
  klineData: KlineData[];
  period: '1d' | '1m';
  
  // 分析
  analysisDays: number;
  analysisResult: AnalysisResult | null;
}
```

---

## 设计完成

准备开始实施。
