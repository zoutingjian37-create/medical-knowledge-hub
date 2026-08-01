---
name: Medical Knowledge Hub
description: 面向医学科研内容采集、提炼与 Obsidian 归档的本地工作台
colors:
  primary: "#087e78"
  primary-strong: "#05645f"
  primary-soft: "#e6f3f1"
  neutral-canvas: "#f4f6f7"
  neutral-surface: "#ffffff"
  neutral-muted: "#eef2f3"
  neutral-ink: "#17233a"
  neutral-ink-soft: "#637083"
  neutral-line: "#dce3e6"
  neutral-line-strong: "#cbd5d9"
  semantic-success: "#18724e"
  semantic-danger: "#b33b32"
typography:
  headline:
    fontFamily: "Segoe UI Variable, Segoe UI, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "32px"
    fontWeight: 760
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Segoe UI Variable, Segoe UI, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "18px"
    fontWeight: 720
    lineHeight: 1.35
  body:
    fontFamily: "Segoe UI Variable, Segoe UI, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.65
  label:
    fontFamily: "Segoe UI Variable, Segoe UI, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "13px"
    fontWeight: 650
    lineHeight: 1.5
rounded:
  sm: "8px"
  md: "12px"
  pill: "999px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "20px"
  lg: "26px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.neutral-surface}"
    rounded: "{rounded.sm}"
    padding: "11px 18px"
  button-primary-hover:
    backgroundColor: "{colors.primary-strong}"
    textColor: "{colors.neutral-surface}"
    rounded: "{rounded.sm}"
  navigation-active:
    backgroundColor: "{colors.primary-soft}"
    textColor: "{colors.primary-strong}"
    rounded: "{rounded.sm}"
    height: "42px"
  surface-panel:
    backgroundColor: "{colors.neutral-surface}"
    textColor: "{colors.neutral-ink}"
    rounded: "{rounded.md}"
    padding: "24px 26px"
---

# Design System: Medical Knowledge Hub

## Overview

**Creative North Star: "科研索引台"**

界面像一张可靠的科研资料工作台：任务入口按研究工作顺序排列，状态明确，装饰克制。视觉服务于采集、提炼、确认和归档，不把操作型产品包装成营销首页。

系统采用中等偏高的信息密度。冷白工作面承载长时间阅读，墨蓝形成清楚层级，青绿色只标记当前导航、主操作和真实状态。熟悉的侧栏、表单、列表和面板帮助用户直接进入任务。

**Key Characteristics:**

- 稳定的左侧导航和清晰的主任务区
- 以索引行和分隔组织信息，避免等权卡片陈列
- 仅使用一种青绿色强调色
- 固定字号层级和短促状态动效
- 小屏切换为顶部横向导航和单列内容

## Colors

冷调中性色提供安静的研究环境，青绿色承担操作与状态，不作无意义装饰。

### Primary

- **研究青绿** (`primary`): 用于主按钮、当前导航、关键操作状态。
- **深青绿** (`primary-strong`): 用于悬停、强调文字和高对比状态。
- **浅青绿** (`primary-soft`): 用于当前选择和主任务的低强度背景。

### Neutral

- **工作台底色** (`neutral-canvas`): 全局页面背景。
- **内容工作面** (`neutral-surface`): 面板、表单和导航底色。
- **次级工作面** (`neutral-muted`): 次操作和悬停区域。
- **主墨色** (`neutral-ink`): 标题和关键内容。
- **辅助墨色** (`neutral-ink-soft`): 说明、元数据和辅助文字。
- **分隔线** (`neutral-line`, `neutral-line-strong`): 列表、区域和步骤连接。

**The One Accent Rule.** 青绿色只表达当前、可执行或真实状态；普通说明和非活动区域保持中性。

## Typography

**Display Font:** Segoe UI Variable，中文回退到 PingFang SC 与 Microsoft YaHei
**Body Font:** 与 Display Font 相同

**Character:** 单一系统无衬线字体保证 Windows 高缩放下的清晰度。层级来自稳定的字号和字重，不使用展示字体或夸张字距。

### Hierarchy

- **Headline** (760, 32px, 1.2): 页面级任务标题，移动端收至 27px。
- **Title** (720, 18px, 1.35): 面板标题和主要内容分组。
- **Body** (400, 15px, 1.65): 页面说明，最长约 68 个字符。
- **Label** (650, 13px, 1.5): 导航、按钮、步骤和状态。

**The Fixed Product Scale Rule.** 操作页面使用固定字号层级；响应式变化来自结构重排，而不是连续缩放标题。

## Layout

桌面端使用 248px 固定侧栏，内容区最大宽度 1260px。首页主任务区采用约 1.75:0.8 的双列结构，采集入口领先，工作流程支持；下方工具以三列索引区继续任务。

间距以 8px、12px、20px、26px 为主。标题与说明紧密，面板之间留出 20px，页面边缘使用更宽的 32px 以上空间。1080px 以下主任务转为单列，900px 以下侧栏收为顶部导航，680px 以下所有内容和工具转为单列。

**The Task Order Rule.** 页面视觉顺序必须与采集、提炼、确认、归档的真实操作顺序一致。

## Elevation & Depth

深度由工作面色差和低强度环境阴影共同表达。导航和列表内部优先使用分隔线；只有整块主要面板获得统一的柔和阴影。

### Shadow Vocabulary

- **Panel Ambient** (`0 12px 32px rgba(32, 52, 65, 0.06)`): 仅用于主页级工作面板。

**The Quiet Depth Rule.** 同一容器只选择阴影或明显边框作为主要深度信号，不叠加发光和硬投影。

## Shapes

控件使用轻微圆角。常规按钮、输入和索引容器使用 8px；主要面板使用 12px；胶囊形仅用于短状态和小型行内操作。没有装饰性异形或大面积玻璃效果。

## Components

### Buttons

- **Shape:** 紧凑矩形按钮，轻微圆角 (8px)。
- **Primary:** 研究青绿底色、白色文字，常用内边距为 11px 18px。
- **Hover / Focus:** 悬停转为深青绿；键盘焦点使用半透明青绿色外圈；按下位移 1px。
- **Secondary:** 浅青绿底色和深青绿文字。

### Chips

- **Style:** 仅用于短操作或状态，使用胶囊形和中性或青绿填充。
- **State:** 青绿表示当前主操作，中性表示次操作。

### Cards / Containers

- **Corner Style:** 主要面板 12px，内部索引组 8px。
- **Background:** 内容工作面或浅青绿主任务面。
- **Shadow Strategy:** 只有页面级工作面板使用 Panel Ambient。
- **Border:** 索引组使用 1px 中性分隔线。
- **Internal Padding:** 主要使用 20px 到 26px。

### Inputs / Fields

- **Style:** 白色底、1px 中性边框、8px 圆角。
- **Focus:** 边框转研究青绿，并出现低强度青绿色焦点圈。
- **Error / Disabled:** 错误使用语义红；禁用降低透明度并保留文字可读性。

### Navigation

桌面端为固定左侧栏，活动项使用浅青绿背景、深青绿文字和 3px 状态线。移动端改为单行可横向滚动的顶部导航，活动项保留颜色但移除状态线。

### Task Index Row

任务索引行以标题、短说明和右侧动词组成。首要任务使用浅青绿工作面和青绿动词控件；次任务使用中性工作面。行之间使用单条分隔线，不拆成独立卡片。

## Do's and Don'ts

### Do:

- **Do** 先突出当前最可能执行的任务，再展示解释和工具。
- **Do** 用接近关系和单条分隔线组织同类动作。
- **Do** 为 hover、focus、active、disabled、error 和真实状态提供明确反馈。
- **Do** 在窄屏保持 DOM 顺序与视觉任务顺序一致。

### Don't:

- **Don't** 把所有功能做成同等大小的营销卡片。
- **Don't** 添加没有真实数据来源的指标、进度或活跃度。
- **Don't** 用第二种强调色装饰普通区域。
- **Don't** 为操作型页面添加展示字体、渐变文字或无目的入场动画。
