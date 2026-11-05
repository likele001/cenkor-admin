# Cenkor Admin 系统更新日志

> **唯一事实源**：本文件顶部为最新版本。发版时在标题行下方插入新版本段，后台首页「系统更新日志」公告约 30 秒内自动同步（无需重启服务、无需人工改公告）。
>
> 版本段格式：
>
> ```markdown
> ## YYYY-MM-DD　标题（⭐ = 重点版本）
>
> **【分组名】**
>
> - 要点一
> - 要点二
> ```

## 2026-11-05　发版链路加固：版本漂移闸门 + 反代文档

**【修复】**

- 模板市场提交页：已登录的 admin 账号提交应用会被错认成 `user_id` 相同的开发者，现限制仅门户（开发者）账号可提交
- 后台「内容管理 → 模板市场」切换 Tab 后，已安装卡片串到「下载主题」页一页排开，已按 `activeTab` 隔离

**【发版机制】**

- `release.sh` 新增 `sync` / `check` 子命令：`sync` 按当前 VERSION 对齐 release.json，`check` 只读校验漂移（退出码 1，可进 CI）
- `release.sh` 在「VERSION 已是目标版本」时不再直接退出，改为继续同步 release.json，堵住「bump 一半」
- 版本文件读取容忍 CRLF（Windows `core.autocrlf=true` 会把 VERSION 读成 `0.5.20\r` 这种毒值）
- CI 新增第三道闸门：`release.json.version` 必须等于 `VERSION`，否则中断发版，防止发布页贴成上一版说明
- 修复发布页 Docker 镜像名缺 owner：`ghcr.io/cenkor-admin-backend:<ver>` → `ghcr.io/likele001/cenkor-admin-backend:<ver>`

**【文档】**

- 新增「宝塔 Nginx 反代与伪静态配置说明」：三条铁律、站点全景表、反代与伪静态代码、`$` 锚定事故复盘、变更 SOP、curl 验证清单、9 条故障速查

**【工程化】**

- ruff 全量清零：导入排序 + 未使用解包变量

**【注意】**

- 无数据库迁移，升级后重启后端即可生效
- 本次含前端改动（admin-web），升级需同步更新 `frontend/admin-web/dist`，否则 Tab 串页修复不生效

## 2026-11-04　模板市场：主题模板上架 + 一键安装 ⭐

**【新增：模板市场】**

- 商店新增第三类商品 `theme`（主题模板），与「平台应用」「产品扩展」并列
- `theme.json` 声明配色 / 排版 / 文案配置项，安装后在「主题配置」出表单，换配色不用碰代码
- 新增 `theme_install.py`：安装即解包进站点主题目录并写注册表，重复安装覆盖旧版，不会叠出一堆目录
- 免费包直接落盘、付费包走授权码，两条路径共用同一套包校验器
- 后台「内容管理 → 模板市场」：浏览官方目录、看详情、一键安装

**【新增：开发者侧】**

- 开发者门户补「发布主题模板」独立入口，提交页支持 `dev_method=theme`
- 开发文档新增「主题模板」（目录结构、`theme.json` 全字段、页面映射、上下文与数据 API、widget 沙箱、调试自检）与「市场商业化」（上架流程、注册、定价抽成、授权码、结算）两章
- 提交记录与「我的应用」增加交付类型徽标，主题 / 平台扩展 / 独立应用一眼区分

**【新增：官方样例主题】**

- 墨痕 Inkwell：博客杂志风，衬线标题 + 暖纸底 + 墨蓝主色，列表支持 magazine / classic 两种排布
- 青云 Qingyun：企业官网，靛蓝青渐变 Hero 双 CTA + 数据亮点条 + CTA 横幅，10 项可配置

**【注意】**

- 无数据库迁移，升级后重启后端即可生效
- 自托管部署必须显式配置 `MARKET_HUB_URL`。未配置时后端回退到默认域名拉官方目录，那个域名只有前端 SPA，`/api/v1/store/apps` 会返回 HTML，进后台模板市场就报「官方应用市场返回了非 JSON 内容」

## 2026-11-04　版本对比 + 站内搜索词闭环 + 官网产物移出仓库 ⭐

**【新增：稿件版本对比】**

- 新增 `GET /cms/entries/{id}/versions/diff?from=&to=`，按块级标签切行做 diff：标题、正文、摘要、`custom_fields`、`seo` 逐项对齐
- 后台版本历史里点「对比」打开双栏弹窗，左右同一行对齐，新增绿底、删除红底，不用手动同步滚动
- 解决的是审核流形同橡皮图章的问题：之前只能看到「有 v3」和「回滚到 v3」，看不到 v3 改了哪一句

**【新增：站内搜索词日志】**

- 新增 `cms_search_logs` 表，记录归一化后的查询词（小写 + 压空白）、结果数、访客标识
- `/public/search` 旁路写入，写日志失败只告警，绝不影响搜索本身
- 新增 `GET /cms/ai/search-terms`，返回热词榜、零结果词、搜索概览与清理入口
- 选题缺口页改成双数据源：语义反推（原有）+ 真实搜索词（新增），后者能看到「用户搜了但站内没有」的真实需求

**【优化：官网构建产物移出 git】**

- `frontend/landing/` 里 70 个构建产物不再入库，只保留 6 个不参与构建的手写页
- 打包脚本改为从磁盘收集，跟另外三套前端一致；仓库不再每次构建就新增一批哈希文件

**【注意】**

- 本次含数据库迁移 `20261104_1100_cms_search_logs`，升级后需执行 `alembic upgrade head` 并重启后端

**【新增：AI 事实溯源】**

- 新增 `POST /cms/ai/entries/{id}/fact-check`：把正文里没有依据的具体说法指出来 —— 百分比、数字+单位、年月日、版本号、英文专名、引号引语逐项核对
- 两段式：先按规则与证据做确定性比对（零成本），没兜住的句子才交给模型判定，且模型只能引用代码给的编号，越界引用一律剔除
- 依据按可信度排：起草素材 > 企业知识库 > 站内已发布内容。三个证据源都为空时直接判风险并说明原因，不去打扰模型
- **只提示不阻断发布**。核验本身有误判空间（行业公知、纯观点稿），硬卡发布只会让编辑关掉这个功能

**【修复：打包漏掉官网文档中心】**

- `build-frontends.sh` 同步 landing 时的排除清单把 `docs-content/` 和 `favicon / robots.txt / sitemap.xml / og-image.png` 当成「不参与构建的静态资产」排除了。实际上它们都是 `landing-web` 的构建源（`docs:sync` 生成 + `public/` 目录），v0.5.15 把产物移出 git 后，干净环境里就不再存在，包内文档中心整个缺席
- 排除清单收敛到 6 个真正的手写页；新增打包自检：landing 文件数不达标直接中止，不再「包能打出来、装上缺内容」

## 2026-11-04　依赖安全加固清零 critical + 改写稿 Markdown 渲染 + 内链建议修复 ⭐

**【安全：Dependabot 告警 100+ → 7，critical 与 high 全部清零】**

- `dompurify` 3.4.13 → 3.4.17（**critical**，SAFE_FOR_TEMPLATES 策略绕过）——这个库正是用来净化 AI 生成正文的，属于可直接被利用的 XSS 通道，优先修
- `axios` 1.17.0 → 1.21.0（13 条告警）、`markdown-it`、`liquidjs`、`vue` / `@vue/server-renderer` 同步升到修复版本
- `vite` 5.4.21 → 6.4.5：vite 5 已停止维护，安全公告只回补到 6.4.4+，留在 5.x 无论怎么升都清不掉。三个 web、脚手架模板、后端内嵌前端（cloud_storage / codegen）全部统一
- `@vitejs/plugin-vue` 4.x → 5.2.4：4.x 不兼容 vite 6，脚手架模板与内嵌项目一并修正
- `vue-i18n` 9.14.5 → 11.x：9.x 已 EOL，新公布的 advisory 没有修复版本。三个前端都是 `legacy: false` 的 Composition API，迁移无额外改动，`globalInjection`（模板里的 `$t`）在 v11 仍保留
- 新增 9 条 `overrides`，把传递依赖钉在修复版本，避免下次安装又回退
- 删除两份从不参与安装的遗留 lock：`frontend/landing-web/package-lock.json`（workspace 成员，构建实际用根 lock）与 `frontend/admin-web/pnpm-lock.yaml`（pnpm 时期残留且仍被跟踪）。Dependabot 一直在读它们，报出一批永远装不到机器上的版本

**【新增：改写稿支持 Markdown 渲染】**

- 新增 `src/lib/markdown.ts`：marked 解析 + DOMPurify 净化 + 结果缓存
- `RichTextContent` 增加 `format="markdown"` 模式，原有 `auto` / `html` 行为不变
- 接到改写稿再分发正文与 AI 工作台草稿正文：此前裸用 `whitespace-pre-wrap`，`**加粗**`、列表、标题都被原样显示成源码

**【修复：内链建议在推理模型下必然失败】**

- `ai/internal_link.py` 的 `max_tokens` 从 4000 提到 16000
- 推理模型光思考就能吃掉 1.4 万字符，预算一满只返回 `reasoning_content`、没有正文，前端表现为「AI 调用失败」。这是 100% 复现的必然失败，不是偶发
- 修复后内链建议立即恢复产出（清单一篇稿件补 2 条内链、3 个标签，线上验证通过）

**【优化：后台首页欢迎语对齐 AI CMS 定位】**

- 旧平台名文案换成「欢迎回来。AI CMS 已就绪，去创作或管理内容吧。」，中英文同步
- 清理 `_extracted` 字典里 4 条携带旧品牌名的失效 key，构建产物中旧名 0 处残留

**【验证】**

- 三个前端 `vue-tsc` + build 全部通过；landing 的 SSR 预渲染正常产出 7 页
- 线上 `admin.cenkor.cn` 登录页文案全部渲染，console 0 error 0 warning（重点核 i18n v11 的 `$t`）
- Dependabot 剩余 7 条全是 medium / low，卡在 `echarts` 6、`@unhead/vue` 2、`@tiptap/*` 3、`minimatch` 11 这几个跨大版本升级，单独排期，不混进这类批量 PR
- 后端 Python 改动只有一处 `max_tokens`，需重启服务生效，无数据库迁移

## 2026-11-03　CI 门禁恢复绿：入仓代码的 lint 清理与密钥扫描误报

**【修复：GitHub 密钥扫描误报，push 被反复告警】**

`backend/src/cenkor_admin/apps/payment/drivers/wechat.py` 里有处微信 AppID
占位符 `wx1234567890abcdef`——18 位、`wx` + 16 位十六进制，正好命中 GitHub
的「腾讯微信 API 应用 ID」规则。它只是驱动里的示例，不含任何真实凭据，
但告警会一直挂在仓库首页。

- 占位符改成 `wx1234567890abcd`（共 18 位，`wx` + 14 位），换掉那个刚好
  撞规则的“太工整”的 16 位十六进制，并补一句注释说明为什么不写满
- 全仓复核已跟踪文件：仅此 1 处命中，无真实 AppID / AppSecret / 私钥
- **已经产生的告警不会自动消失**，需在仓库 Security → Secret scanning 里
  手动标记为误报（API 操作需要仓库权限 token，服务器上没有）

**【修复：payment / commerce 入仓后 CI Lint 首次失败】**

这两个应用此前被 `.gitignore` 排除，CI 在干净 checkout 里根本看不到它们。
v0.5.11 开源入仓后第一次进入 lint 视野，一次性暴露 108 处历史告警。

- `RUF100` 多余 `noqa` 59 处、`I001` 导入排序 12、`UP017` 12、`UP037` 12、
  `C416` 5，其余 8 处 —— `ruff --fix` 自动修 116，手工处理 11
- 其中 `F841` 是真问题：`pricing = {}` 声明后从未被使用，实际走的是
  `price_map`，直接删掉
- 全部是等价重写，不改任何运行时行为

**【修复：本地跑绿、CI 跑红的判定漂移】**

清完上面那批后本地 `ruff check` 干净，CI 仍报 2 处 `I001`。根因不在代码本身：

- ruff 的 isort 会**自动探测**哪些是 first-party 包，依据是 `src/` 下的目录内容
- 本地 `backend/src/` 多了未跟踪的 `apps/`，判定结果与干净 checkout 不一样
- 在 `pyproject.toml` 显式声明 `known-first-party = ["cenkor_admin", "apps"]`，
  不再让本地工作区内容影响判定

排查手法值得记住：用 `git archive HEAD | tar -x` 还原一份与 CI 完全一致的
文件树，在副本上跑门禁——只有这样才能复现「CI 独有」的失败，本地跑永远带着
未跟踪目录，结论不可信。

**【验证】**

- 主仓库与干净副本，`ruff check` 均 `All checks passed`
- pytest 1 failed / 185 passed / 36 skipped / 11 errors，与改动前基线一致
- CI 四个 job（Backend(PG) / admin-web / portal-web / Integration）全绿
- **纯后台等价重写：不需要重启服务，也不涉及任何数据库迁移**

## 2026-11-03　迁移规范按真实拓扑重写，废弃会自动顺延的 rebase_closed_chain

**【文档】两份迁移文档仍在教「两条链、一个挂载点」的旧模型**

v0.5.11 开源 payment/commerce 时迁移图被重构过（公开链合流 + 闭源三条支线），
但 `database-migrations.md`（权威版）和 `migrations.md`（历史记录）都没跟上。
照旧文档操作会直接把图改坏，所以按实测拓扑整体重写。

- 总 100 个迁移：公开 59、闭源 41；公开子图单根单 head（`20261027_0100_app_schema`）
- 闭源侧是**三条锚点固定的支线**：erp/crm/mes → `0035_app_publish`、
  workflow → `0025_cloud`、collect → `0100_app_schema`，
  最后在 `20261103_1300_merge_closed` 汇合成单 head
- 新增公开迁移**不再需要动任何闭源文件**，「顺延挂载点」这一步彻底删除
- 顺手补上此前漏登记的 `collect`：目录表、忽略规则、闭源理由都补齐了

**【代码】废弃 `rebase_closed_chain`：它会让新迁移被静默跳过**

`codegen/builder.py` 里这个函数会在内置模式生成迁移后，把「`down_revision` 恰好
等于公开 head 的闭源迁移」改挂到新迁移下面。

v0.5.11 之后 collect 支线的锚点**就是**公开 head，一旦触发：collect 支线被拖到新迁移
之下 → 新迁移进入闭源合流点 `merge_closed` 的祖先闭包 → 已部署库 `upgrade heads`
判定它「已应用」，**不报错、不建表**，直到代码查那张表才 500。

- 函数改为恒返回空列表并写明原因，`scripts/gen-app.py` 不再调用
- 新增公开迁移只需把 `down_revision` 设成公开 head，别的都不用动

**【实测】纯公开链建库**

`git archive HEAD` 导出公开文件树 → 空库 → `alembic upgrade head`：
59 个迁移建 **101 张表**、闭源表 **0 张**、退出码 0。
（v0.5.11 之前是 39 迁移 / 59 表，涨上来是 payment/commerce 开源的结果，
不是建库逻辑变了。）

## 2026-11-03　迁移图收尾：闭源链合流为单 head，检查规则改为「公开严格、闭源放宽」

**【迁移图】v0.5.11 开源 payment/commerce 时留下的三个孤立 head**

那版为了让公开视图不断链，改挂了两个 `down_revision`：`commerce_0020` 从
`mes_0009` 改挂公开合流点，`product_commerce_0029` 从 `workflow_0027` 改挂
`cloud_0025`。改挂是对的，副作用是两个原挂载点失去子节点，加上本来就是 head 的
`collect_1100`，全量视图出现 3 个 head，`check-migration-graph.py` 全量模式报错。

- 新增闭源合流迁移 `20261103_1300_merge_closed`（`down_revision` 指向上述三个），
  `upgrade` / `downgrade` 均为空实现，**不产生任何 DDL**
- 该文件不进公开仓库（父节点是未跟踪的 revision，进库会让公开视图断链），
  已在 `.gitignore` 逐个登记
- 没有改回原挂载方式：那会让公开链重新依赖闭源 revision，公开仓库直接断链，
  比多几个 head 严重得多

**【检查规则】从「两种视图都必须单 head」改为「公开严格、闭源放宽」**

- 硬约束收敛为一条：git 跟踪的迁移（公开子图）必须恰好 1 个 head、无断链 ——
  公开仓库拉下来要能一把建库，这条破了就是事故
- 全量视图允许多个 head：erp / crm / mes / workflow / collect 是并行开发线，
  各自一个 head 是正常形态，不必强迫合流
- 全量视图新增一项校验：每个 head 都必须能沿 `down_revision` 回到公开 head，
  不能有与公开链平行的孤链

**【修掉一处自己的漏检】**

原实现只把全量断链放进问题列表，公开子图的断链算了却没用。后果：公开迁移的
`down` 指向「工作区里有、git 里没有」的闭源 revision 时，全量图看着完整、
公开视图实际是断的，**直接放行** —— 而这正是本脚本要防的头号事故。
已补 `public_broken` 分支，报错单列「工作区在、clone 不在」这个陷阱。
另补 6 个场景的规则测试（临时 git 仓库构造迁移图），合法放行、非法拦截。

**【清理】删掉 `backend/scripts/check-migration-graph.py`**

与根 `scripts/` 那份是两份**不同的实现**，从 v0.3.0 起就分叉了。根目录那份一直在
演进，backend 那份自 v0.3.0 没再改过。确认零引用（pre-commit、打包脚本、
15 处文档引用全部指向根 `scripts/`，无 Python import）后删除。留着会让打包带上
两个同名不同行为的脚本，改门禁时改错文件。

**【升级说明】**

生产库当前 `alembic_version` 是 3 行，跑 `alembic upgrade heads` 会执行 1 条空 op
迁移，version 表收敛为 1 行（`20261103_1300_merge_closed`），**不重跑任何既有迁移**。
实测：表数 241 不变，3 秒完成，二次执行 0 条。已部署环境重启也无感 ——
`migration_runner` 看到 `pending=0` 直接跳过。

## 2026-11-03　支付中心与应用交易层开源：payment / commerce 随仓交付（⭐）

**【开源范围变更】收款能力是底座，不该收在闭源里**

支付中心 `apps/payment`（支付宝官方 / 微信支付官方 / 虎皮椒聚合三通道 +
收银台 + 订单 + 通道配置，3398 行）与生态交易层 `apps/commerce`
（定价 / 订单 / 授权签发 / 云端绑定，4994 行）此前源码放在外置目录、
被 `.gitignore` 整体排除。本次一并迁回内置目录，与平台同 MIT 授权，
**不单独收费、不需要授权码**。

- 源码位置：`backend/src/apps/{payment,commerce}/`
  → `backend/src/cenkor_admin/apps/{payment,commerce}/`
- 顺带清掉 4 个历史 `.bak_*` 手工备份（本就不该跟着源码流浪）
- `static/apps/payment/plugin.js`、`docs/05-用户手册/payment_操作手册.md`
  一并入库随包交付

> 为什么不给支付单独留个授权位：`payment/manifest.py` 里它自己标着
> `builtin=True`（"删了商店/套餐/订单付不了账"）。底座不开源、却把下游应用
> 标成商业闭源，买到商业应用的用户也跑不起一笔结算 —— 逻辑上是拧着的。

**【安全】授权体系：开源 77 行签发逻辑，但私钥不入库**

`commerce/license_authority.py` 是 Ed25519 私钥生成 + 签名签发，
文件头原本写着「只部署在授权中心」。本次判断可以开源，理由记在这里：

- 私钥**不在源码里**：`get_or_create_keypair` 首次调用时现场生成，
  以密文存进 `system_settings.license.signing_key`，随部署环境走
- 客户实例只内置**公钥**（`core/licensing.DEFAULT_PUBLIC_KEY_B64`）做验签
- Ed25519 的安全性只依赖私钥保密，不依赖算法实现保密（Kerckhoffs 原则）——
  拿到全部源码但没有私钥，依然伪造不出有效授权
- 反过来，不开源会让自营部署签不出授权，商店功能是残的

**【修复】迁移图合流：公开链恢复单 head**

开源后这些迁移要进公开仓库，但它们挂在闭源链中间，父节点拿不到：

| 迁移 | 原 `down_revision` | 问题 |
|---|---|---|
| `20260922_0020_commerce` | `20260904_mes_0009` | ERP→CRM→MES 闭源链尾 |
| `20261007_0029_product_commerce` | `20260925_0027_workflow` | workflow 仍闭源 |

直接改挂到公开链尾会切断 erp/crm/mes 与主链的连接，它们变成「未应用分支」，
`upgrade heads` 会把 ERP 全部迁移重跑一遍（撞 `DuplicateTable`）。故新增
合流迁移 `20261103_1200_merge_commerce`：把公开链并行的两条分支
（`20261103_1100_cms_orphan` 与 `20261020_0035_app_publish`）并成一个点，
commerce 段挂到合流点之后，`product_commerce_0029` 改挂它真正依赖的
`20260924_0025_cloud`。

- 公开视图：59 个迁移，**单 head** `20261027_0100_app_schema`，无断链
- 完整视图：`mes_0009` / `workflow_0027` / `collect_1100` 三个 head，
  `upgrade heads` 各自独立推进
- `alembic_version` 由 `(collect, cms_orphan)` 迁移为
  `(mes_0009, workflow_0027, collect)`；实测 `upgrade heads` 零 DDL

**【校验】开工前对支付应用做了敏感信息扫描**

- 无私钥 / 证书文件（`-----BEGIN PRIVATE KEY-----` 只是配置项的 placeholder 文案）
- 无硬编码密钥、商户号（正则扫 `secret|apikey|appsecret|mch_id` 赋值，零命中）
- 配置全部走 `settings` / 环境变量，敏感值用 Fernet（密钥由 `SECRET_KEY`
  经 PBKDF2 派生）加密存储

**【文档】口径同步**

- `README.md`：许可适用范围里支付从「需单独授权」移入「已开源不收费」，
  补上 workflow / collect 两个此前漏登记的闭源项
- `CONTRIBUTING.md`：分层表格新增"改支付中心 / 应用交易层 ✅ 欢迎"一行
- `docs/packaging.md`、`docs/apps/development_guide.md`：闭源清单去掉 payment
- 代码注释 19 处 + `license_authority.py` 模块文档重写（原「闭源」定性已不成立）

---

## 2026-11-03　新增 CONTRIBUTING.md：贡献入口与提交门禁（⭐）

**【新增】根目录 `CONTRIBUTING.md`（193 行）**

把「提交前必须知道的硬约束」集中到一处，省得每个贡献者重新踩一遍：

- **分层说明**：哪些目录可以直接提 PR（核心 / 前端 / 新增 App / 驱动插件），
  哪些（ERP / CRM / MES / 支付 / 开发者门户）**不在仓库内**、提不了。
  并点明改 `apps/base.py` 的 `AppManifest` 契约会波及仓库外的商业应用，
  这类改动需在 PR 里说明兼容性影响
- **七道门禁**：与 CI 逐条对应的可复制命令（`pip check` / `ruff check` /
  `check-migration-graph.py` / `alembic upgrade heads` /
  `check-orm-drift.py` / 单元测试 / 前端 `type-check` + `build`），
  并说明 6 个集成测试需真 uvicorn + seed、本地 skip 或报错属正常
- **迁移改动**：改了 models 就必须同时有迁移，否则 alembic 不报错、单测测不到，
  只有 ORM 漂移检查会红（引用 `migrations.md` 与
  `database-migrations.md` §12.1，不重复正文）
- **提交信息**：Conventional Commits + 中文，附 6 条真实历史提交作示例；
  特别提醒「别整文件改写行尾」—— 仓库有部分 CRLF 文件，
  一个改 3 行的提交会变成 2000 行 diff
- **贡献授权**：提交 PR 即视为按 MIT 授权（inbound = outbound），
  当前**不要求签署 CLA**，将来若引入会事先在文件里说明
- **禁止提交**：密钥 / 生产数据 / 构建产物 / 闭源代码；
  并给出「密钥已误提交 → 先当它已泄漏、立刻轮换，再处理 git 历史」的处置顺序

**【入口】**

- README 顶部导航新增「🤝 参与贡献」一行，与「文档索引 / 迁移规则 / 打包交付」并列

**【核对】**

- 文档内 7 个相对链接 + 2 个代码路径**全部实测存在**，0 死链
- `check-migration-graph.py --tracked-only`（49 迁移 / 单 head）、
  `check-doc-facts.py`（33 份文档 / 260 表 / 69 路由）、
  `check-app-tracking.sh` 全绿
- README 保持 LF 行尾，diff 仅 **+1 行**；新文件为 LF

## 2026-11-03　许可证声明补齐：明确 MIT 的适用范围（⭐）

**【核对结论：确实是 MIT，且分发合规】**

- `LICENSE` 为标准 MIT 全文，`Copyright (c) 2026 李可乐`
- GitHub 识别 `spdx_id = MIT`，仓库 public
- `backend/pyproject.toml` 的 `license = "MIT"` 与之一致
- 实测 v0.5.8 发行包（1098 条目）：根目录带 `LICENSE` 且内容完整，
  **无任何闭源代码混入**，MIT 要求「所有副本附带版权声明」这一点是满足的

**【修复：两处声明缺失】**

- `frontend/admin-web`、`design-tokens`、`landing-web`、`portal-web`
  四个 `package.json` 补 `"license": "MIT"`。此前 npm 生态与 SPDX 扫描工具
  读到的是 `UNKNOWN`
- `frontend/developer-web` **刻意不加**：它是闭源资产、在 `.gitignore` 里，
  标 MIT 会与商业授权冲突
- README 许可章节新增「适用范围」：说明许可仅覆盖仓库内 git 跟踪的内容，
  ERP / CRM / MES / 支付 / 开发者门户不在仓库内、不适用本许可、需单独授权；
  并提醒混合部署场景下不要误读根目录 `LICENSE`

**【为什么补适用范围】**

MIT 只覆盖实际存在于仓库的文件，闭源代码不在仓库 → 法律上没问题。
但客户拿到「开源内核 + 商业应用」混装时，根目录的单个 `LICENSE`
容易被理解为对全部目录的授权，进而以为有权再分发商业应用。
写清边界比事后解释便宜。

## 2026-11-03　依赖门禁：CI 与升级路径双双加对账（⭐）

**【背景：上一轮的 4 条冲突是怎么漏过去的】**

出事前 `pip check` 报 4 条，但没有人在日常流程里跑它。补门禁时先做了实测，
结论比预想的更值得记一笔：

- **CI 里加 `pip check` 抓不到那次事故**。干净环境里 `boto3>=1.34.0` 没有上界，
  pip 直接解到 `boto3 1.43.117` + `aiobotocore 3.10.0` + `botocore 1.43.117`，
  三者自洽，`pip check` 输出 `No broken requirements found`
- 生产那 4 条冲突的真身是**环境漂移**：`aiobotocore` 长期停在 2023 年的 2.5.0
  （钉死 `botocore 1.29.76`），声明 `>=2.5.0` 并未被违反，所以任何只看声明的检查
  都不会报警
- **顺带查出一个更严重的隐患**：旧声明在全新环境解出的是 `aiobotocore 3.10.0`，
  而生产跑的是 2.26.x —— CI 与生产测的根本不是同一个大版本的 S3 SDK。
  v0.5.7 补的 `aiobotocore>=2.26.0,<3` 上界恰好把这处对齐了，属意外收获

**【改动】**

- `.github/workflows/ci.yml`：依赖安装后新增 `pip check` 步骤。定位是保险，
  不是主力——它能挡的是「多步安装中后一步把前一步的包降级」这类破损元数据
- `scripts/upgrade.sh`：依赖安装前存 `pip freeze` 快照到
  `$BACKUP_DIR/req-before-<时间戳>.txt`，安装后跑 `pip check` 对账。
  **漂移发生在增量升级路径上，所以真正的拦截点在这里**；冲突时逐条打印并给出
  用快照回滚依赖的确切命令
- 冲突不阻断升级（打印警告），与脚本原有的「依赖安装报错可忽略」策略保持一致

**【验证】**

- 复刻 CI 环境（py3.12 + `requirements.txt` + CI 专用工具）`pip check` 干净，
  确认新门禁不会让现有流水线变红
- 从 `upgrade.sh` 里抽出真实代码块跑了两个分支：干净环境输出「✓ 依赖自洽」；
  用 `pip install --no-deps boto3` 造出破损环境后，逐条列出 3 项缺失并打印回滚命令
- `bash -n scripts/upgrade.sh` 通过；`ci.yml` YAML 解析通过，CRLF 行尾保持

## 2026-11-03　依赖清理：pip check 归零，S3 链路升到 aiobotocore 2.26（⭐）

**【修复：4 条 pip check 冲突，根子只有一个】**

- 起因：`pip check` 报 4 条 broken requirements，看似四个独立问题
- 根因：`aiobotocore 2.5.0` 钉死 `botocore>=1.29.76,<1.29.77`（**精确到单个补丁版本**），
  而 botocore 1.29.76 又钉死 `urllib3<1.27`，于是三面撞车：
  `boto3` 要 botocore ≥1.34、`s3transfer` 要 ≥1.33.2、
  `trafilatura` / `htmldate` 要 urllib3 ≥2.8.0
- 删掉 `boto3` 声明：代码里**零引用**，唯一依赖者是 `kombu[sqs]` 的 extra，
  项目用 `celery[redis]`，从未启用
- `aiobotocore` `>=2.5.0` → `>=2.26.0,<3`，连带 `botocore 1.29.76 → 1.41.5`、
  `urllib3 1.26.20 → 2.8.0`
- 为什么 2.26 能解开 urllib3 死结：botocore 1.41 的 `urllib3<1.27` 带
  `python_version < "3.10"` 条件，本项目跑 3.13，**条件不生效**
- 上界 `<3` 是必须的：2.x 每个版本钉一个 botocore，不加上界时全新环境
  会直接解到 3.10.0（botocore 1.43.x），与现存行为差一个大版本

**【验证：先独立 venv 跑通，再动生产】**

- 目标组合（aiobotocore 2.26.0 / botocore 1.41.5 / urllib3 2.8.0 /
  trafilatura 2.3.1 / htmldate 1.11.0 / requests 2.34.2）`pip check` 无冲突
- 用项目真实 `S3CompatDriver` 跑 10 项全过：health_check / ensure_bucket /
  upload_fileobj / head_object / get_object 内容一致 / list_objects /
  presigned_put_url / presigned_get_url / copy_object / delete
- 生产真实链路（`QiniuKodoDriver` + 凭证解密）：上传、直连签名 URL 回读、
  公有 URL 回读全部 200 且内容一致
- `trafilatura` 在 urllib3 2.8.0 下 `extract` / `bare_extraction` 正常
- 后端测试与升级前**完全一致**（185 passed / 36 skipped / 1 failed / 11 errors，
  均为既有的 aiosqlite 缺失与 sqlite 方言环境问题）
- 升级后 `pip check`：**No broken requirements found**

**【顺带发现一个既有瑕疵（本轮未修）】**

- `presigned_get_url` 生成后会经 `_apply_cdn_domain` 把 host 换成 CDN 域名，
  而 CDN 不认识 S3 签名参数 → 该 URL 返回 404
- 实测同一对象：直连签名 URL **200**、公有 URL **200**、CDN 变换 URL **404**
- 私有对象的签名访问应走直连 endpoint，CDN 域名只适合公有读；单独排期修

## 2026-11-03　bcrypt 4.1+ 兼容：口令上下文收敛 + 垫片（⭐）

**【修复：passlib 版本探测告警】**

- 现象：seed 首次建管理员、或服务首次 hash/verify 口令时打印
  `(trapped) error reading bcrypt version`
- 根因：`passlib/handlers/bcrypt.py:620` 读 `bcrypt.__about__.__version__`，
  bcrypt ≥ 4.1 已删除 `__about__`；passlib 捕获后走「版本未知」分支
- 功能本就正常，但日志噪音会掩盖真实故障，且说明跑在**未声明**的版本上

**【改动】**

- 新增 `core/pwd.py`：全站唯一 `CryptContext`，导入时补回 `__about__` 垫片
- `core/security.py`、`apps/portal/auth.py` 原先**各建一份** `CryptContext`，
  改为复用同一实例——参数一旦分叉，典型症状就是「改完密码登录不了」
- 依赖约束 `bcrypt>=3.2.0,<4.0` → `bcrypt>=4.1,<5`
  （`<5` 是为规避 bcrypt 5.0 把超 72 字节口令由「静默截断」改为「抛 ValueError」）
- 新增 `tests/test_password_context.py`：垫片在位 / 单实例 / 跨模块 `$2b$` 互通

**【取 B 方案：放宽约束，而不是降级 bcrypt】**

- 备选 A（重装 3.2.x）能让告警消失，但等于把环境钉回两年前的版本，
  后续任何依赖 bcrypt 4.x 的包都会再撞一次
- 选 B：放宽声明 + 兼容垫片，环境与声明一致，且前向兼容到 4.x 任意小版本
- **哈希输出仍是 `$2b$12$`，历史口令零迁移**

**【验证】**

- 生产库实测：`auth_users` 29 条、`portal_users` 24 条，全部 `$2b$12$`，
  `pwd_context.identify()` 均返回 `bcrypt`
- 对照实验：裸 passlib 复现 `AttributeError: module 'bcrypt' has no attribute
  '__about__'`；走 `core.pwd` 则静默、哈希与校验全部正常
- ruff 全绿；`test_password_context.py` 3 条 + `test_security.py` 3 条全过

## 2026-11-03　交付文档修正：包内迁移 head 不再写死（⭐）

**【修正：PACKAGE.md 声称的 head 已过期】**

- v0.5.3 往公开链末尾补了 `20261103_1100_cms_orphan`，但 `scripts/package-core.sh`
  里 PACKAGE.md 的文案仍写死「迁移链唯一 head 为 `20261031_1600_cms_permalink`」
- 后果：每个 Release 包的说明都在告诉用户一个**过期 head**，照此核对会误以为包是旧的
- 改为打包时实算：head 取自 `check-migration-graph.py --tracked-only`，
  迁移数取自 `git ls-files`，两者一起写进 PACKAGE.md
- `docs/packaging.md` 里同样的写死示例（「44 个迁移」/旧 head）改为占位表述，
  并明确「不要在文档里写死 revision，迁移一加就会过期」

**【验证：把 Release 包真装一遍】**

- 下载 v0.5.4 的 Release 资产（`cenkor-admin-core-0.5.4-20261103.tar.gz`，4.1 MB），
  在空库上走完整路径：`alembic upgrade heads` → `seed`
- 结果：49 个迁移全部执行、head `20261103_1100_cms_orphan`、86 张基表、
  v0.5.3 补的 6 张表与 18 个字段齐全、seed 全绿
  （permissions 48 / menus 50 / roles 3 / users 1 / store listed=9 manifests=9）、
  ORM 漂移 79 张全绿、幂等复跑 no-op
- 包内无 erp / crm / mes / workflow / payment，也无 `src/apps`，闭源未泄漏

**【已知噪音，不是缺陷】**

> **已由 v0.5.6 修复**：口令上下文收敛到 `core/pwd.py` 并补 `__about__` 垫片，
> 依赖约束放宽为 `bcrypt>=4.1,<5`。以下为当时的分析，保留备查。

- seed 首次创建管理员时会打印 `(trapped) error reading bcrypt version`：
  passlib 1.7.4 读 `bcrypt.__about__.__version__`，而 bcrypt ≥ 4.1 已移除该属性。
  功能正常（passlib 内部已捕获，seed 退出码 0）。
  `requirements.txt` 已 pin `bcrypt>=3.2.0,<4.0`，按文档安装不会遇到；
  当前服务器实装 4.3.0 属「环境与声明不一致」，需单独对齐。

## 2026-11-03　漂移检查修正：ERP 视图不再误报缺表（⭐）

**【修正：20 个「缺表」其实是视图】**

- `scripts/check-orm-drift.py` 原先只用 `inspect.get_table_names()`（只返回基表），
  把 ERP 透传 MES 真表的 20 个 `erp_*` **视图**误判成「缺 20 张表」，
  于是一装 ERP 门禁就红，告警等于失效
- 实测这 20 个对象：全部可读、`pg_relation_is_updatable = 28`
  （INSERT / UPDATE / DELETE 全通）、且都带业务数据（工单 12 行、追溯 12 行、
  BOM 7 行）——ERP 一直正常在用，**不存在缺表**
- 它们由 `apps/{erp,crm,mes}/schema.sql`（方案 D）在应用启动时创建，
  对应 `AppManifest.schema_managed=True`，alembic 主链刻意不建、也不纳入 diff

**【检查逻辑加固】**

- 关系对象判定扩为「表 / 视图 / 物化视图」，视图不再被当成缺失
- 新增 `schema_managed` 应用识别：这类表缺失归入提示级
  `MISSING_SCHEMA_MANAGED`，不计为迁移责任（应用未启动过时属正常）
- 输出增加「库中基表数 / 关系对象合计 / 经视图映射 / schema.sql 托管」四项，
  一眼分清「真缺失」与「误判」
- 验证：生产库 214 张 ORM 表全绿（其中 20 张经视图映射，
  `schema.sql` 托管 107 张）；开源包等价环境 79 张仍全绿，无回归

## 2026-11-03　开源包结构完整性 + CI 门禁（⭐）

**【迁移：补齐 6 张表与 18 个字段】**

- 在「开源包全新安装」环境里做 ORM ↔ 库结构逐项比对，发现一批对象
  **任何迁移都没建过**（公开链、闭源链都没有）——生产库是历史上靠手工 SQL
  补出来的，仓库里只留 ORM 定义。这类缺口 alembic 不会报错、单元测试也测不到，
  只有真连库比对才露出来
- 补齐：`cms_kb_docs` / `cms_kb_chunks` / `cms_publish_channels` /
  `cms_publish_jobs` / `cms_entry_stats_daily` / `cms_track_events` 共 **6 张表**；
  `app_submissions`(5) / `cms_ai_generations`(4) / `cms_entries`(2) /
  `cms_forms`(2) / `cms_pages`(5) 共 **18 个字段**，外加 2 个外键
- 其中 `app_submissions` 的 5 列原先只由**闭源迁移**添加，而公开侧 seed
  （内置应用自动上架）要用它们 —— 开源版每次 `seed` 都会报
  `UndefinedColumn: schema_version`。现在公开链自备一份
- 结构全部由生产库 `pg_dump --schema-only` 导出，不凭 ORM 反推；
  重复主键会抛 `42P16 invalid_table_definition`（**不是** `duplicate_object`），
  DO 块已把四类冲突异常全收
- pgvector 缺失时 `cms_kb_chunks.vector` 降级为 `double precision[]`
  （与既有方案一致），装扩展后用 `backend/scripts/enable_pgvector.py` 升级

**【CI：迁移必须覆盖 ORM 全部定义】**

- 新增 `scripts/check-orm-drift.py`：拿 SQLAlchemy metadata 与真实库逐表逐列
  比对，`MISSING_TABLE` / `MISSING_COLUMN` 一律失败
- 接入 CI 的 `ORM ↔ 迁移 漂移检查` 步骤（在迁移执行之后、跑测试之前）
- 这才是这类问题的门禁：`alembic upgrade heads` 只要迁移图自洽就返回成功，
  它并不知道 ORM 里还有别的表

**【修复：Release 流水线已连续 3 个版本失败】**

- 根因：`scripts/build-frontends.sh` 用 `rsync -a --delete` 同步 landing 产物，
  把 `frontend/landing/` 里**不参与构建**的资产（5 个旧静态页、
  `docs-content/` 文档源、`robots.txt` 等）全删了；随后 `package-core.sh`
  用 `git ls-files | tar` 打包，撞上已不存在的文件，报
  `tar: frontend/landing/advantages.html: Cannot stat` 而中止
- 后果：v0.5.0 / v0.5.1 / v0.5.2 的 Docker 镜像都推送成功，
  但 **GitHub Release 与核心包全部没有产出**
- 修法：`rsync --delete` 配排除清单，只清理构建产物；`package-core.sh`
  增加前置检查，发现「git 跟踪但磁盘已删除」的文件时直接指明原因与恢复命令，
  不再让 tar 抛一堆 `Cannot stat`

## 2026-11-03　产品核心能力归入底座（⭐）

**【内置清单：6 个】**

- 新标记 `builtin=True`：`cms`（辰科官网 CMS，AI 内容核心）、`collect`（内容采集）、
  `cloud_storage`（云存储）、`notification`（站内通知）、`payment`（支付中心），
  连同此前的 `sso`，共 **6 个底座能力不可卸载 / 不可停用**
- 仍可装卸的 9 个：`crm` / `erp` / `mes`（商业化业务应用），
  `workflow` / `announcements` / `tickets` / `links` / `quick_notes` / `my_todo`（可选工具）
- 判定标准仍是那句：**能被卸载的是应用，不能卸载的是底座**。
  自己是做 AI CMS 的，把 CMS / 采集这类立身之本做成可卸的商业应用没有意义

**【加固：外部应用的 manifest 会被升级覆盖】**

`collect` / `payment` 在 `backend/src/apps/`（`.gitignore` 第 75 行忽略），
应用中心升级或重装会**覆盖其 `manifest.py`**，写在里面的 `builtin=True` 会丢。
为此新增 `BUILTIN_APP_KEYS` 兜底名单，`is_builtin_app()` 判定 = manifest 声明
**或** 名单命中 —— 两层保险，升级后保护不丢

**【澄清：这 7 个不需要标】**

`rbac` / `system` / `auth` / `portal` / `builder` / `comments` / `forms` 没有
`manifest.py`，不进应用中心，本来就不可能被卸载 —— 不需要也不应该标 builtin。
另 `commerce` 同理，由 `api/v1/__init__.py` 直接挂载

## 2026-11-03　统一登录归入底座能力

**【应用中心 · 内置能力】**

- `AppManifest` 新增 `builtin` 字段，立一条标准：**能被卸载的是应用，不能卸载的是底座**。
  与目录位置无关 —— 放 `apps/` 只是复用 manifest 的自动注册能力
  （路由门禁 / 权限码 / 菜单 / hook），不代表它该被商业化装卸
- 统一登录（SSO）标记 `builtin=True`：应用中心归入「内置功能」分组，排在最前，
  带「内置」徽标，**不渲染卸载 / 停用入口**；`uninstall` / `disable` 接口直接返回
  403，防止绕过 UI 直接打接口
- 启动时自动对齐内置应用状态：被手工改库或老版本 API 停用 / 卸载过的，重启即
  拉回 `installed + enabled`，不影响其他应用，不删任何业务数据

**【为什么不能可卸载】**

登录是系统入口。停用后 `/api/v1/sso/*` 会 403（后台配置页打不开），而
`/api/v1/public/sso/*` 是匿名路由、不受门禁约束（这是刻意的，否则停用后没人
能登进去把它启用回来）—— 两者叠加就是「前台还能扫码登录、后台配置页却消失」
的半死状态。与其靠注释提醒运营别点，不如从语义上禁止。

## 2026-11-03　第三方登录（⭐）

**【统一登录 · 可插拔渠道】**

- 新增「统一登录」：前台支持微信、抖音、飞书、Google、GitHub 五个渠道，
  后台保留账号密码为主、飞书可选。登录属于底座能力（`builtin=True`），
  应用中心不可卸载 / 停用，启动时自动对齐到启用态
- 加一个渠道只需在 `apps/sso/providers/` 放一个文件，不用改路由、前端、数据库 ——
  渠道用目录扫描自动发现，单个渠道加载失败只跳过不阻断启动

**【安全设计】**

- 后台**不开放第三方自助注册**：扫码进来查不到绑定一律拒绝并提示联系管理员。
  后台账号是权限载体，必须由超管创建并分配角色
- 登录成功后**不把 token 放 URL**，改为 2 分钟一次性票据，前端拿票据换 JWT ——
  避免 token 进入浏览器历史、Nginx 日志和 Referer
- state 一次性校验（防 CSRF）+ PKCE（飞书/Google/GitHub，防授权码截获）；
  微信与抖音不支持 PKCE 故关闭
- 第三方邮箱与本站账号冲突时只留空、**不自动合并**，防邮箱抢占
- 渠道密钥加密入库，后台仅回显末四位；`redirect` 参数只接受站内相对路径防开放重定向
- 微信与抖音禁止在后台开放（C 端账号体系不适合当管理入口），配置层强制拦截

**【数据】**

- 绑定表补 `raw_profile` / `last_login_at`，`auth_user_oauth` 补上
  `UNIQUE(provider, open_id)` 与外键 —— 原表注释写了唯一约束但实际从未建过，
  并发下会插重复行导致查询报错

**【后台】**

- 系统 → 登录方式：填一次回调域名，五个渠道的回调地址自动生成；
  渠道特有项（微信扫码/公众号两种模式、Google 是否申请离线访问）由后端声明下发

**【升级提示】**

- 升级后重启后端，侧栏「系统」组会出现「登录方式」入口（启动自动对齐补菜单）
- 需在后台填入各渠道 AppID/AppSecret 后才会在登录页显示按钮；
  未配置时登录页与原来完全一致，账号密码登录不受影响
- 微信需企业认证（300 元/年）、抖音需企业主体 + 网站备案，两者回调地址必须 HTTPS

## 2026-11-02　菜单入口全量补齐（8 项）

**【平台 · 修复】**

- 补回 8 个「有页面、无菜单入口」的功能：在线升级、事件推送、URL 重定向、评论管理、表单问卷、代码生成、URL 规则、页面构建
- 根因：这些页面前端路由一直都在，菜单定义却只存在于生产数据库（早年在「菜单管理」里手工加的行）。代码里的种子清单没有它们，全新部署侧边栏自然看不到入口
- 对账口径升级为「前端路由 × 生产库菜单 × 种子清单」三方比对，不再逐个发现逐个补
- 修复后全新库验证：105 张表 + seed → 菜单 49 条，「系统」组 14 项齐全，顺序按 sort 正确排列
- 老库无影响：生产库同步预演「菜单新建 0 个」，既有菜单与角色绑定保持不变
- 新增启动时自动对齐：后端启动按 app manifest + 核心种子重放菜单与权限（幂等、只补不删、不覆盖运营在菜单管理里调过的顺序），以后改菜单升级重启即生效，不必再手工跑同步脚本

## 2026-11-02　内链模块 + URL 规则体系 + 标签聚合 ⭐

**【内容运营 · 内链】**

- 内链升级为独立模块：向量召回候选文章 → 模型精选并生成锚文本与插入位置 → 编辑页一键插入正文或保存待审，支持通过 / 拒绝 / 标记已插入 / 删除
- 新增 `cms_entry_links` 表，用部分唯一索引排除 rejected，拒绝后可重新建议，不会卡死
- 内链关系可管理、可筛选、带状态计数；后续沉淀为标签资产，为标签聚合页做流量承接
- 历史文章内链回填脚本（幂等、支持 --dry-run），存量已回填 36 条

**【SEO · URL 与聚合页】**

- 栏目级 URL 规则可视化配置，支持按栏目配置文章永久链接格式与模板
- 标签聚合页上线并纳入 sitemap 收录

**【平台 · 修复】**

- 修复新装实例 14 个 AI 页面侧栏无入口：seed 与 manifest 两套菜单清单补齐「AI 内容中心」分组
- 补齐 AI 层 12 张表的建表迁移（批量生产 / 记忆 / 定价 / 质检 / 会话 / AB 测试 / 内容摘要 / 工作流编排），干净环境安装后即可用，不再报「表不存在」

**【运维】**

- CI lint 门禁转绿，修复 ruff 12 处告警
- 仓库停止跟踪前端构建产物，减少 2 万余行噪音

## 2026-11-02　全自动发布模式 + 图片转存云存储 + AI 自动配图 ⭐

**【采集应用 collect · 全链路】**

- 全自动发布模式：规则可选三档（不自动 / 自动改写转草稿 / 自动改写并发布），定时抓 → 改写 → 配图 → 发布无人值守；每轮 5 条成本护栏，失败标记跳过不重试，调度器补扫防丢
- 正文图片转存云存储：外站图自动转自有 CDN，同图缓存幂等、单图失败兜底不阻塞；含存量文章一次性回填（29 张）
- AI 自动配图：正文无图时自动生成头图，插正文首图 + 挂 SEO 社交分享封面
- 修复空壳检测误杀英文站、外链清洗误删 HTML 图片等问题
- 采集操作手册上线文档站（docs.user.023ent.net）

**【工作台首页】**

- 系统更新日志自动化：本文件为唯一事实源，公告自动同步，发版零人工
- 首页 API 统计图去噪：排除钩子事件（HOOK）与门户公开接口流量，趋势窗口修正为真实 7 天

## 2026-11-01　采集箱操作闭环 + AI 改写 / 聚合 + JS 渲染通道 ⭐

**【采集应用 collect · 全链路】**

- 可视化采集规则：数据项点选式编辑（CSS / XPath / 正则多选自动回退）+ 数据处理动作点选（替换 / 截取 / 反转义 / 填充等），试采集面板逐步 trace
- 定时采集（分钟级）+ 采集箱操作闭环：AI 改写 / AI 聚合 / 转草稿 / 发布 / 批量操作
- AI 聚合：2~8 条同主题素材融合为综述条目（新条目落箱、带溯源）
- JS 渲染采集通道（browser）：无头浏览器抓取单页应用，「渲染等待」毫秒可调
- 外链三道防线清洗：入箱清洗 / AI 改写禁链 / 转草稿兜底，正文外站超链接零残留

## 2026-10-31　采集应用（collect）开发启动

- 可视化点选式规则引擎 + 定时采集

## 2026-09-24　应用商店 / 应用中心重构 + 商业生态层落地 ⭐

- 商店公开只读接口、门户应用中心收编、搜索筛选 facets、详情页版本/权限/安装状态
- 商业生态层：定价 / 订单 / 支付 / 授权 license / 开发者收益 / 云端安装
- 可插拔应用三层机制体检通过，商店在架 12 应用全部已安装

## 2026-09-04　应用商店体系落地：MES 制造执行首个独立可插拔应用 v1.0.0 ⭐

- BOM / 工艺路线 / 生产订单 / 生产计划 / 排产派工 / 生产报工 / 车间看板
- 「上传 ZIP → 审核 → 安装」一键流程，路由 / 前端 / 迁移自动注册

## 2026-08-08　内容编辑器 + 全量移动端响应式 + 工作台更新日志 ⭐

- TipTap 富文本编辑器替换后台 9 处长文本字段，图片直传云存储
- 侧边栏抽屉化、表格横滚、grid 响应式；工作台首页直接展示更新日志

## 2026-07-02　V2 架构文档更新与重构

## 2026-06-09　通知中心 / API Key 管理 / 系统设置 / 后台增强

## 2026-06-08　项目初始化（Cenkor Admin Platform 单体仓库）
