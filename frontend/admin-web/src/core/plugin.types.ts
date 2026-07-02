/** App 前端插件合约 */
export interface PluginDefinition {
  /** App 唯一标识 */
  id: string
  /** 版本号 */
  version: string
  /** 路由定义（会被添加到 admin-web 路由表） */
  routes?: PluginRoute[]
  /** 国际化消息 */
  locales?: Record<string, Record<string, string>>
  /** 菜单项（合并到侧边栏） */
  menus?: PluginMenuItem[]
  /** App 名称 */
  name?: string
}

export interface PluginRoute {
  path: string
  name: string
  component: () => Promise<any>
  meta?: Record<string, any>
}

export interface PluginMenuItem {
  key: string
  title: string
  path: string
  icon?: string
  parentId?: number | null
  sort?: number
}

/** 后端返回的已安装 App 插件信息 */
export interface InstalledPlugin {
  key: string
  name: string
  version: string
  script_url: string
}
