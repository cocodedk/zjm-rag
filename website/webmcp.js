// WebMCP: typed, read-only tools for an AI agent in the visitor's browser, so it can read this page
// instead of scraping it. Every answer is read from the page at call time; nothing here makes a request.
// Spec (a draft that has already moved once): https://webmachinelearning.github.io/webmcp/
// The tool list is mirrored in /llms.txt; change both together.

const text = (el) => (el ? el.textContent.replace(/[\u200e\u200f]/g, '').replace(/\s+/g, ' ').trim() : '');
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
// An element's status comes from its nearest data-state, so moving an interface between the lists is enough.
const state = (el) => (el?.closest('[data-state]')?.dataset.state === 'available' ? 'available' : 'planned');
const NO_INPUT = { type: 'object', properties: {}, additionalProperties: false };
const READ_ONLY = { readOnlyHint: true };
const NAMES = ['describe', 'get_install_command', 'list_interfaces'];

// An interface's summary is its list item without the spec link.
function summary(li) {
  const copy = li.cloneNode(true);
  copy.querySelectorAll('a.spec').forEach((a) => a.remove());
  return text(copy);
}

function tools() {
  return [
    {
      name: 'describe',
      title: 'What is on this page',
      description: 'Returns what this zjm-rag page is about, its language, its sections and the other tools, in the page language.',
      inputSchema: NO_INPUT,
      annotations: READ_ONLY,
      execute: async () => ({
        ok: true,
        page: 'zjm-rag',
        language: document.documentElement.lang || 'en',
        title: text($('h1')),
        summary: text($('.lede')),
        status_note: text($('.hero-note')),
        sections: $$('main section').map((s) => ({
          id: s.id || s.getAttribute('aria-labelledby') || '',
          heading: text(s.querySelector('h2')),
        })),
        tools: NAMES,
      }),
    },
    {
      name: 'get_install_command',
      title: 'Install command',
      description: 'Returns the command that installs the zjm_rag Python library today, its requirements, and whether the one-line installer is available yet; it runs nothing.',
      inputSchema: NO_INPUT,
      annotations: READ_ONLY,
      execute: async () => ({
        ok: true,
        command: $('[data-install]')?.textContent.trim() ?? '',
        status: state($('[data-install]')),
        requirements: $$('[data-requirements] li').map(text),
        one_line_installer: state($('[data-interface="mcp"]')),
      }),
    },
    {
      name: 'list_interfaces',
      title: 'Ways to use zjm-rag',
      description: 'Lists the four ways to call zjm-rag (Python library, CLI, HTTP JSON API, MCP server), each with whether it is available or planned, a summary, its spec link and an example if there is one.',
      inputSchema: NO_INPUT,
      annotations: READ_ONLY,
      execute: async () => ({
        ok: true,
        interfaces: $$('[data-interface]').map((li) => ({
          name: li.dataset.interface,
          status: state(li),
          summary: summary(li),
          spec: li.querySelector('a.spec')?.href ?? '',
          example: $(`[data-example="${li.dataset.interface}"]`)?.textContent.trim() ?? '',
        })),
      }),
    },
  ];
}

// Resolves to the names the browser really holds. Fired and forgotten, so it never rejects.
export async function initWebMcp() {
  const registry = document.modelContext;
  if (!registry || typeof registry.registerTool !== 'function') return [];
  await Promise.all(tools().map((tool) => Promise.resolve()
    .then(() => registry.registerTool(tool))
    .catch(() => { /* one refused tool must not take the others with it */ })));
  const held = await Promise.resolve().then(() => registry.getTools()).catch(() => []);
  return (Array.isArray(held) ? held : []).map((t) => t && t.name).filter((n) => NAMES.includes(n));
}

initWebMcp();
