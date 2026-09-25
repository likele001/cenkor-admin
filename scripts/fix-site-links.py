#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档站后处理：修正 md 内的本地链接。

VitePress 会把「本地 .md 链接」当成页面引用去做动态 import —— 目标不存在时
不是跳过，而是直接 ERR_MODULE_NOT_FOUND 让整站构建失败（ignoreDeadLinks 也拦不住）。
本脚本做两件事：

  1. 路径修正：仓库根级文件同步后落在站点同级，`../X.md` → `./Y.md`；
     子目录里的 `../../` → `../`。
  2. 死链降级：目标的 .md / 目录都不存在时，把 `[文字](目标)` 降级为纯文字，
     避免构建失败；外链 / 锚点原样保留。
"""
import os
import re
import sys

LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')

# 键＝仓库里的名字，值＝同步后站点上的名字。
# 仓库根级文件（architecture.md / admin_system_comparison.md）同步后落在
# 站点目录同级，引用要从 `../X` 改成 `./X`。
# README.md 是特例：仓库保留大写（GitHub 约定，外部 blob 链接依赖它），
# 站点侧由同步脚本小写化为 readme.md，所以键值大小写不同。
ROOT_FILE_MAP = {
    'architecture.md': 'architecture.md',
    'admin_system_comparison.md': 'admin_system_comparison.md',
    'README.md': 'readme.md',
}


def normalize(src):
    """仓库结构 → 站点结构 的路径修正。"""
    for old, new in ROOT_FILE_MAP.items():
        src = src.replace(f'](../{old})', f'](./{new})')
        src = src.replace(f'](../{old}#', f'](./{new}#')
    # 子目录文档（apps/ addons/ release/）里的 ../../ → ../
    src = src.replace('](../../', '](../')
    return src


def fix_links(path):
    src = normalize(open(path, encoding='utf-8').read())
    original = src
    base = os.path.dirname(path)
    dropped = []

    def repl(m):
        text, target = m.group(1), m.group(2)
        if target.startswith(('http://', 'https://', 'mailto:', '#', '/')):
            return m.group(0)
        anchor = ''
        if '#' in target:
            target, a = target.split('#', 1)
            anchor = '#' + a
        if not target:
            return m.group(0)
        cand = os.path.normpath(os.path.join(base, target))
        checks = [cand]
        if not cand.endswith('.md'):
            checks += [cand + '.md', os.path.join(cand, 'index.md')]
        if any(os.path.exists(c) for c in checks):
            return m.group(0)
        dropped.append(target)
        return text

    src = LINK_RE.sub(repl, src)
    if src != original:
        open(path, 'w', encoding='utf-8').write(src)
    return dropped


def main():
    dest = sys.argv[1] if len(sys.argv) > 1 else '/www/wwwroot/knowledge/docs/cenkor-admin'
    if not os.path.isdir(dest):
        print(f'  ✗ 目录不存在: {dest}')
        sys.exit(1)
    changed = 0
    all_dropped = []
    for root, _dirs, files in os.walk(dest):
        for name in sorted(files):
            if not name.endswith('.md'):
                continue
            dropped = fix_links(os.path.join(root, name))
            if dropped:
                changed += 1
                rel = os.path.relpath(os.path.join(root, name), dest)
                print(f'    {rel}: 降级 {len(dropped)} 个死链 → {", ".join(dropped[:3])}'
                      + (' …' if len(dropped) > 3 else ''))
                all_dropped += dropped
    print(f'  ✅ 处理 {changed} 个文件，共降级 {len(all_dropped)} 个死链')


if __name__ == '__main__':
    main()
