/** API snake_case ↔ 前端 camelCase 转换 */

export function toProductPayload(form: {
  name: string
  chineseName?: string
  slug: string
  tagline: string
  line: string
  stack: string
  desc: string
  features: string[]
  isFlagship: boolean
  isOpenSource: boolean
  github: string
  demo: string
  website: string
  license: string
  sort: number
  status: string
  custom_fields?: Record<string, any>
}) {
  return {
    name: form.name,
    chinese_name: form.chineseName || null,
    slug: form.slug,
    tagline: form.tagline,
    line: form.line,
    stack: form.stack,
    desc: form.desc,
    features: form.features,
    is_flagship: form.isFlagship,
    is_open_source: form.isOpenSource,
    github_url: form.github || null,
    demo_url: form.demo || null,
    website_url: form.website || null,
    license: form.license || null,
    sort: form.sort,
    status: form.status,
    custom_fields: form.custom_fields,
  }
}

export function fromProductApi(data: Record<string, unknown>) {
  return {
    name: data.name as string,
    chineseName: (data.chinese_name as string) || '',
    slug: data.slug as string,
    tagline: data.tagline as string,
    line: data.line as string,
    stack: (data.stack as string) || '',
    desc: data.desc as string,
    features: (data.features as string[]) || [],
    isFlagship: !!data.is_flagship,
    isOpenSource: !!data.is_open_source,
    github: (data.github_url as string) || '',
    demo: (data.demo_url as string) || '',
    website: (data.website_url as string) || '',
    license: (data.license as string) || '',
    sort: (data.sort as number) ?? 0,
    status: (data.status as string) || 'published',
    custom_fields: (data.custom_fields as Record<string, any>) || {},
  }
}

export function fromProductListItem(p: Record<string, unknown>) {
  return {
    id: p.id as number,
    key: (p.key || p.slug) as string,
    name: p.name as string,
    chineseName: (p.chinese_name as string) || null,
    tagline: p.tagline as string,
    line: p.line as string,
    desc: p.desc as string,
    isFlagship: !!p.is_flagship,
    status: p.status as string,
    sort: p.sort as number,
  }
}
