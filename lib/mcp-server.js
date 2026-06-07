#!/usr/bin/env node
/** 华尔街驻铁岭办事处 MCP Server — 标准 MCP 协议实现 */

const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const { ListToolsRequestSchema, CallToolRequestSchema } = require('@modelcontextprotocol/sdk/types.js');
const fs = require('fs');
const path = require('path');

const skillPath = path.join(__dirname, '..', 'SKILL.md');
const skillContent = fs.readFileSync(skillPath, 'utf-8');

const TOOLS = [
  {
    name: 'due_diligence',
    description: '企业尽调：对指定企业进行全方位背景调查，返回工商/股权/诉讼/财务/风险分析。格式: HTML(苹果液态玻璃风)/Word(公文排版)/Markdown/PDF/纯文本',
    inputSchema: {
      type: 'object',
      properties: {
        company_name: { type: 'string', description: '企业名称或统一社会信用代码' },
        depth: { type: 'string', enum: ['quick', 'standard', 'deep'], description: '快速/标准/深度扒光', default: 'standard' },
        format: { type: 'string', enum: ['html', 'word', 'markdown', 'pdf', 'text'], description: '输出格式', default: 'markdown' }
      },
      required: ['company_name']
    }
  },
  {
    name: 'people_investigation',
    description: '人员背景调查：对指定人员进行全维度背景穿透，返回身份/任职/司法/社交/资产分析',
    inputSchema: {
      type: 'object',
      properties: {
        name: { type: 'string', description: '姓名' },
        id_number: { type: 'string', description: '身份证号(可选)' },
        phone: { type: 'string', description: '手机号(可选)' }
      },
      required: ['name']
    }
  },
  {
    name: 'financial_analysis',
    description: '财务分析：五维财务分析(偿债/盈利/现金流/粉饰识别/趋势对标)',
    inputSchema: {
      type: 'object',
      properties: {
        company_name: { type: 'string' },
        years: { type: 'number', default: 3 }
      },
      required: ['company_name']
    }
  },
  {
    name: 'anti_nominee_detection',
    description: '反代持穿透：识别股权代持关系，突破实控人隔离',
    inputSchema: {
      type: 'object',
      properties: {
        company_name: { type: 'string' }
      },
      required: ['company_name']
    }
  },
  {
    name: 'load_skill',
    description: '加载华尔街驻铁岭办事处完整技能定义，获取13人团队全部能力和铁律',
    inputSchema: {
      type: 'object',
      properties: {
        brief: { type: 'boolean', description: '是否精简版(Token友好)', default: false }
      }
    }
  }
];

const server = new Server(
  { name: 'wallstreet-tieling', version: '1.0.0' },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  switch (name) {
    case 'load_skill': {
      const content = args?.brief
        ? skillContent.substring(0, 3000) + '\n\n[... SKILL.md 精简加载，完整版约15,000字符 ...]\n'
        : skillContent;
      return {
        content: [{ type: 'text', text: content }]
      };
    }
    case 'due_diligence':
    case 'people_investigation':
    case 'financial_analysis':
    case 'anti_nominee_detection': {
      // 返回技能激活指令 + 任务描述
      const instructions = [
        `📋 任务激活: ${name}`,
        `参数: ${JSON.stringify(args)}`,
        ``,
        `请以「华尔街驻铁岭办事处」13人团队模式执行此任务。`,
        `团队: 钱守正(总经理)→陈志远(拆解)→张铁柱+李明远+王思远+赵刚+马力全+周通(业务组)→刘文华(报告)→颜好看(设计)→郑慎之(审计) | 吴德厚(PUA监督)+暗哨(独立监控)`,
        `铁律: 不编造数据、不输出信贷决策、所有数据标注来源、推论须经三步法`,
        ``,
        skillContent.substring(0, 500)
      ].join('\n');
      return {
        content: [{ type: 'text', text: instructions }]
      };
    }
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('🏛️  华尔街驻铁岭办事处 MCP Server 已启动');
}

main().catch(console.error);
