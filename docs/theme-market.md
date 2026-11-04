# 模板市场

模板市场是站长安装第三方主题、开发者上架自己主题的地方。

## 功能概览

| 角色 | 功能 |
|---|---|
| 站长 | 浏览主题、一键安装、管理已装主题 |
| 开发者 | 提交主题、查看下载量、设置定价、申请提现 |
| 平台 | 审核主题、管理定价、处理提现 |

## 站长视角

### 浏览与安装

1. 后台「CMS → 模板市场」
2. 浏览主题（可搜索、按分类筛选）
3. 点「安装」→ 免费主题直接装，付费主题填授权码
4. 安装后可选「立即切换为生效主题」

### 管理已装主题

- 后台「模板市场 → 已装」查看所有已安装主题
- 点主题名进入「模板工作台」编辑
- 在「站点配置」切换生效主题

## 开发者视角

### 注册开发者

1. 后台「模板市场 → 我的模板」
2. 点「注册开发者」
3. 填写显示名称、简介、网站

### 打包主题

主题包是一个 zip 文件，包含：

```
my-theme/
├── theme.json          # 清单文件（必须）
├── layout.html         # 布局模板
├── list.html           # 列表页模板
├── detail.html         # 详情页模板
├── partials/
│   └── header.html     # 公共片段
├── assets/
│   └── style.css       # 样式文件
└── widgets/
    ├── carousel.html   # 组件结构
    └── carousel.js     # 组件脚本（可选）
```

**theme.json 必须包含**：
- `key`：主题唯一标识（小写字母/数字/连字符/下划线）
- `name`：显示名称
- `version`：语义化版本（如 1.2.0）
- `description`：简介
- `author`：作者信息

详细字段说明见[模板开发指南](template-guide.md#122-打包规范themejson)。

### 提交主题

1. 后台「模板市场 → 我的模板 → 提交新版本」
2. 上传 zip 文件
3. 填写版本号、更新日志
4. 系统自动校验（theme.json 结构、路径安全、Jinja 语法、CSP 合规）
5. 审核通过后上架

### 设置定价

1. 后台「市场 → 定价管理」
2. 选择主题
3. 设置定价模式（free / one_time / seat）
4. 设置价格

**平台抽成**：默认 20%，可在「市场设置」调整。

### 查看收入

- 后台「市场 → 开发者 → 我的收入」
- 后台「市场 → 开发者 → 账单明细」
- 后台「市场 → 开发者 → 提现」

## 平台视角

### 审核主题

1. 后台「系统 → 应用中心」
2. 找到待审核的主题
3. 查看校验结果（自动预检）
4. 人工审核：视觉、侵权、描述真实性
5. 通过 / 拒绝

**自动预检项**：
- theme.json 结构合法
- 路径全部通过安全校验
- Jinja 语法正确
- 无内联脚本 / 事件 / 伪协议
- asset_kinds 声明与实际文件一致

### 管理定价

- 后台「市场 → 定价管理」：为每个主题设置价格
- 后台「市场 → 市场设置」：调整平台抽成比例

### 处理提现

- 后台「市场 → 提现管理」
- 审核提现申请
- 确认打款

## 技术细节

### 安装流程

1. 前端调 `POST /api/v1/cms/theme-market/install`
2. 后端从 hub 下载主题包（免费走公开通道，付费走授权码通道）
3. 校验主题包（theme_package.validate_package）
4. 写入 `cms_templates` 表
5. 清除模板缓存

### 数据存储

| 数据 | 存储位置 |
|---|---|
| 主题文件 | `cms_templates` 表 |
| 主题设置 | `cms_sites.settings`（扁平 key：`theme.<key>.<setting>`） |
| 提交记录 | `app_submissions` 表 |
| 定价 | `app_pricing` 表 |
| 收入/账单 | `app_dev_wallet` / `app_dev_ledger` 表 |

### API 端点

| 端点 | 作用 |
|---|---|
| `GET /api/v1/cms/theme-market/catalog` | 浏览主题市场 |
| `POST /api/v1/cms/theme-market/install` | 安装主题 |
| `GET /api/v1/cms/theme-market/installed` | 已装主题列表 |
| `GET /api/v1/store/submissions` | 我的提交列表 |
| `POST /api/v1/store/submissions` | 提交主题包 |
| `GET /api/v1/store/my/income` | 我的收入 |
| `POST /api/v1/store/my/withdrawals` | 申请提现 |
