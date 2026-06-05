#!/usr/bin/env node
/** 华尔街驻铁岭办事处 CLI — 一键加载，即刻可用 */

const fs = require('fs');
const path = require('path');

const skillPath = path.join(__dirname, '..', 'SKILL.md');
const pkg = require(path.join(__dirname, '..', 'package.json'));

function showHelp() {
  console.log(`
🏛️  华尔街驻铁岭办事处  v${pkg.version}
  ─── 银行信贷情报专家团 ───

用法:
  npx wallstreet-tieling                 输出完整 SKILL.md（粘贴到任意AI对话激活）
  npx wallstreet-tieling --copy          复制到剪贴板（macOS/Windows自动检测）
  npx wallstreet-tieling --brief         输出精简版（约500 token，适合8K窗口模型）
  npx wallstreet-tieling --mcp           启动 MCP Server（供Claude Desktop/CodeBuddy调用）
  npx wallstreet-tieling --help          显示帮助

安装:
  npm install -g wallstreet-tieling       全局安装
  npx wallstreet-tieling                  免安装直接使用

更多形态:
  Skill.md: npx skills add Dear-Ded/wallstreet-tieling -g -y
  MCP:      配置 deploy/mcp-server.json
  ChatGPT:  粘贴 SKILL.md 到 Custom GPT Instructions
  Claude:   添加为 Claude Project Knowledge
`);
}

function outputSkill(brief = false) {
  if (!fs.existsSync(skillPath)) {
    console.error('❌ SKILL.md not found');
    process.exit(1);
  }
  let content = fs.readFileSync(skillPath, 'utf-8');
  if (brief) {
    // Extract key parts only
    const parts = content.split('---');
    const fm = parts.slice(0, 3).join('---');
    const core = content.match(/## 一、我是谁[\s\S]{0,500}/)?.[0] || '';
    const rules = content.match(/## 二、铁律[\s\S]{0,800}/)?.[0] || '';
    console.log(fm + '\n\n' + core + '\n\n' + rules);
  } else {
    console.log(content);
  }
}

function copyToClipboard() {
  const content = fs.readFileSync(skillPath, 'utf-8');
  const { execSync } = require('child_process');
  try {
    if (process.platform === 'darwin') {
      execSync('pbcopy', { input: content });
    } else if (process.platform === 'win32') {
      execSync('clip', { input: content });
    } else {
      execSync('xclip -selection clipboard', { input: content });
    }
    console.log('✅ SKILL.md 已复制到剪贴板，粘贴到任意AI对话即可激活');
  } catch (e) {
    console.error('⚠️  无法自动复制，请手动复制 SKILL.md 内容');
    outputSkill(false);
  }
}

// === Main ===
const args = process.argv.slice(2);
if (args.includes('--help') || args.includes('-h')) {
  showHelp();
} else if (args.includes('--copy') || args.includes('-c')) {
  copyToClipboard();
} else if (args.includes('--brief') || args.includes('-b')) {
  outputSkill(true);
} else if (args.includes('--mcp')) {
  require('../lib/mcp-server.js');
} else {
  outputSkill(false);
}
