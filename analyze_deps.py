#!/usr/bin/env python3
"""
模块依赖分析器 - 生成 Mermaid 依赖图
"""
import os
import re
from pathlib import Path
from collections import defaultdict

# 项目根目录
PROJECT_ROOT = Path(__file__).parent

# 要分析的模块（排除测试和多数据源）
MODULES_TO_ANALYZE = [
    'core/engine.py',
    'core/session_bus.py',
    'core/query_cache.py',
    'core/org_memory.py',
    'core/deep_graph.py',
    'core/roles.py',
    'core/rules.py',
    'core/interfaces.py',
    'api/agent.py',
    'api/agent_registry.py',
    'api/config.py',
    'api/orchestrator.py',
    'api/personality.py',
    'adapters/_base.py',
    'adapters/workbuddy.py',
    'adapters/cli.py',
]

def extract_imports(file_path: Path) -> set[str]:
    """提取文件中的 import 语句"""
    imports = set()
    
    try:
        content = file_path.read_text(encoding='utf-8')
    except:
        return imports
    
    # 匹配 import xxx 和 from xxx import yyy
    patterns = [
        r'^import\s+(\S+)',  # import xxx
        r'^from\s+(\S+)\s+import',  # from xxx import yyy
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, content, re.MULTILINE):
            module = match.group(1)
            # 只保留项目内部的模块（core.*, api.*, adapters.*）
            if module.startswith(('core.', 'api.', 'adapters.')):
                imports.add(module.split('.')[0] + '.' + module.split('.')[1] if '.' in module else module)
    
    return imports

def build_dependency_graph() -> dict:
    """构建依赖图"""
    graph = defaultdict(set)
    
    for module_path in MODULES_TO_ANALYZE:
        file_path = PROJECT_ROOT / module_path
        if not file_path.exists():
            continue
        
        module_name = module_path.replace('/', '.').replace('.py', '')
        imports = extract_imports(file_path)
        
        for imp in imports:
            graph[module_name].add(imp)
    
    return graph

def generate_mermaid(graph: dict) -> str:
    """生成 Mermaid 依赖图"""
    lines = []
    lines.append('```mermaid')
    lines.append('graph TD')
    lines.append('    %% 模块依赖图')
    lines.append('    %% 自动生成 - ' + str(Path(__file__).name))
    lines.append('')
    
    # 定义样式
    lines.append('    classDef core fill:#e1f5fe,stroke:#01579b')
    lines.append('    classDef api fill:#f3e5f5,stroke:#4a148c')
    lines.append('    classDef adapter fill:#e8f5e9,stroke:#1b5e20')
    lines.append('    classDef external fill:#fff3e0,stroke:#e65100')
    lines.append('')
    
    # 添加节点（去重）
    all_modules = set()
    for module, deps in graph.items():
        all_modules.add(module)
        all_modules.update(deps)
    
    for module in sorted(all_modules):
        if module.startswith('core.'):
            lines.append(f'    {module.replace(".", "_")}["{module}"]:::core')
        elif module.startswith('api.'):
            lines.append(f'    {module.replace(".", "_")}["{module}"]:::api')
        elif module.startswith('adapters.'):
            lines.append(f'    {module.replace(".", "_")}["{module}"]:::adapter')
        else:
            lines.append(f'    {module.replace(".", "_")}["{module}"]:::external')
    
    lines.append('')
    lines.append('    %% 依赖关系')
    
    # 添加边
    for module, deps in graph.items():
        for dep in deps:
            src = module.replace('.', '_')
            dst = dep.replace('.', '_')
            lines.append(f'    {src} --> {dst}')
    
    lines.append('```')
    return '\n'.join(lines)

if __name__ == '__main__':
    print("🔍 分析模块依赖关系...")
    graph = build_dependency_graph()
    
    print(f"✅ 分析了 {len(graph)} 个模块的依赖关系")
    
    print("\n📊 生成 Mermaid 依赖图...")
    mermaid = generate_mermaid(graph)
    
    output_file = PROJECT_ROOT / 'ARCHITECTURE_DEPS.md'
    output_file.write_text(mermaid, encoding='utf-8')
    
    print(f"✅ 依赖图已保存到: {output_file}")
    print("\n" + mermaid)
