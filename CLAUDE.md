# Claude Code Instructions — Stock Analysis Project

## 文档维护规则（强制）

**每次修改代码后，必须同步更新以下两个文档：**

### `ARCHITECTURE.md`
记录功能设计、模块接口、API、数据流。每次改动后需更新：
- 新增/修改的函数：更新对应模块的函数表
- 新增 API 端点：更新 § 5 API Reference 表格
- 新增 SSE 事件类型：更新 SSE Event Types 表格
- 行为变化（路由逻辑、数据流）：更新 § 3 Data Flow 或对应模块描述
- 新增 Known Quirks：在 § 12 补充条目

### `TECH_STACK.md`
记录技术选型和依赖。每次改动后需更新：
- 引入新的库/框架：更新总览表 + 新增对应章节
- 改变现有技术的使用方式：更新对应章节描述
- 新增依赖版本约束：更新末尾的版本约束表

**规则：代码变更和文档更新必须在同一次对话回复中完成，不能分开。**
