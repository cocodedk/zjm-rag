query groups (1):
Q1 [primary]: which linter checks CSS files
hits: 20

#1 matchedBy=fts+vector agent-linters/llms.txt:1-43
source:
1	# agent-linters
2	
3	> Rewrites linter output as short, imperative prompts, so a coding agent gets
4	> an instruction ("remove unused import `os`") instead of a screenful of
5	> diagnostics. Works at the tool layer — env vars, user-level config, two
6	> PATH shims — so it applies to any agent that shells out to a linter
7	> (Claude Code, Codex, or anything else) without configuring each one
8	> separately. POSIX `sh` + stdlib-only Python 3. No build, no test suite, no
9	> runtime dependencies. MIT licensed.
10	
...

#2 matchedBy=fts+vector agent-linters/README.md:10-32
heading: Website
heading_level: 2
scope: agent-linters
source:
10	## Website
11	
12	- [English](https://cocodedk.github.io/agent-linters/)
13	- [فارسی (Persian)](https://cocodedk.github.io/agent-linters/fa/)
14	
15	```
16	$ lintp src/
17	src/api.py:1     remove unused import `os`
18	src/api.py:14    return str, not int
19	src/ui.tsx:8     add a `key` prop to the list element
...

#3 matchedBy=fts+vector agent-linters/README.md:65-96
heading: lintp
heading_level: 2
scope: agent-linters
source:
65	## lintp
66	
67	Routes by file type and prints one line per finding:
68	
69	| Extensions | Linter |
70	|---|---|
71	| `.py .pyi` | ruff + mypy |
72	| `.js .mjs .cjs .jsx .ts .tsx .mts .cts` | oxlint |
73	| `.css .scss .json .jsonc` | biome |
74	
...

#4 matchedBy=fts+vector agent-linters/bin/lintp:1-45
source:
1	#!/usr/bin/env python3
2	"""lintp — run every linter that applies and print one short imperative line per finding.
3	
4	    $ lintp src/
5	    src/api.py:1   remove unused import `os`
6	    src/api.py:14  return str, not int
7	    src/ui.tsx:8   add a `key` prop to the list element
8	    src/theme.css:1  remove the duplicate CSS property
9	
10	Routing by file type:
...

#5 matchedBy=fts+vector agent-linters/llms.txt:37-73
source:
37	  oxlint is the exception — it only checks the cwd — so `lintp` locates the
38	  nearest `.oxlintrc.json` (or `oxlint.json`/`.oxlintrc`) itself and passes it
39	  with `-c`, rather than forcing its own category flags on top of it.
40	
41	## Rule phrasing tables
42	
43	The imperative wording lives in four dicts near the top of `bin/lintp`, each
44	keyed by the linter's own rule code and mapping to a `(regex, template)` pair
45	(or an ordered list of them) that extracts values out of the linter's message
46	and renders the instruction:
...

#6 matchedBy=fts+vector agent-linters/install.sh:47-102
source:
47	    if [ -L "$dst" ] && [ "$(readlink -- "$dst")" = "$repo/$1" ]; then
48	        rm -f -- "$dst"
49	        echo "  removed  $dst"
50	        # No `&&` chain as the last statement: it returns 1 when there is no backup,
51	        # which under `set -e` would abort the whole uninstall right here.
52	        if [ -e "$dst.bak" ]; then
53	            mv -- "$dst.bak" "$dst"
54	            echo "  restored $dst from .bak"
55	        fi
56	    fi
...

#7 matchedBy=fts+vector agent-linters/website/index.html:97-140
source:
97	        <li><a href="https://github.com/cocodedk/agent-linters">GitHub</a></li>
98	        <li><a href="fa/" class="lang-switch" lang="fa" hreflang="fa">فارسی</a></li>
99	      </ul>
100	    </nav>
101	  </div>
102	</header>
103	
104	<main id="main">
105	
106	  <section class="hero">
...

#8 matchedBy=fts+vector agent-linters/website/index.html:1-30
source:
1	<!doctype html>
2	<html lang="en">
3	<head>
4	<meta charset="utf-8" />
5	<meta name="viewport" content="width=device-width, initial-scale=1" />
6	
7	<!-- SEO keywords:
8	     primary:   linter output for coding agents
9	     secondary: concise ruff output, lintp, agent context window
10	     intent:    informational (how to stop linter noise reaching an agent)
...

#9 matchedBy=fts+vector message-test-plugin/scripts/validate-plugin.py:122-132
source:
122	def check_commands() -> None:
123	    command_dir = PLUGIN / "commands"
124	    files = sorted(command_dir.glob("*.md"))
125	    if not files:
126	        error(f"{rel(command_dir)}: no commands found")
127	    for path in files:
128	        data = split_frontmatter(path)
129	        if data is None:
130	            continue
131	        if not data.get("description"):
...

#10 matchedBy=fts+vector agent-linters/README.md:111-139
heading: Traps worth knowing
heading_level: 2
scope: agent-linters
source:
111	## Traps worth knowing
112	
113	Each of these cost real debugging, and each one made a linter point at the wrong thing.
114	
115	**Never set one shared `MYPY_CACHE_DIR`.** Two projects that each contain a module of the
116	same name — `utils.py`, `main.py`, `conftest.py` — collide in a shared cache, and mypy then
117	reports the finding against *the other project's file*. An agent that trusts the path edits
118	a file in the wrong repository. The shim gives each directory its own cache instead. Note
119	that an inherited `MYPY_CACHE_DIR` wins over the shim, as an explicit setting should — so if
120	you ever exported a shared one, unset it.
...

#11 matchedBy=fts+vector agent-linters/website/index.html:172-212
source:
172	<span class="d">[*] 2 fixable with the `--fix` option.</span>
173	<span class="p">$ mypy src/api.py</span>
174	src/api.py:11: error: Incompatible return value type (got "str", expected "int")  <span class="d">[return-value]</span>
175	<span class="d">Found 1 error in 1 file (checked 1 source file)</span></pre>
176	          </div>
177	
178	          <div class="panel-signal">
179	            <div class="panel-head">
180	              <p class="panel-label">What lintp hands it</p>
181	              <p class="panel-meta">lintp · 5 lines · 155 bytes</p>
...

#12 matchedBy=fts+vector agent-linters/README.md:1-9
heading: agent-linters
heading_level: 1
source:
1	# agent-linters
2	
3	[![CI](https://github.com/cocodedk/agent-linters/actions/workflows/ci.yml/badge.svg)](https://github.com/cocodedk/agent-linters/actions/workflows/ci.yml)
4	[![Pages](https://github.com/cocodedk/agent-linters/actions/workflows/deploy-pages.yml/badge.svg)](https://github.com/cocodedk/agent-linters/actions/workflows/...
5	[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
6	
7	Linter output rewritten as short, imperative prompts, so a coding agent gets an
8	instruction instead of a screenful of diagnostics.
9	

#13 matchedBy=fts+vector agent-linters/shell/linters.fish:1-21
source:
1	# Concise linter output for every tool and every agent. Source from
2	# ~/.config/fish/config.fish, OUTSIDE any `if status is-interactive` block — agents run
3	# fish non-interactively:
4	#
5	#   test -f $HOME/projects/agent-linters/shell/linters.fish
6	#       and source $HOME/projects/agent-linters/shell/linters.fish
7	
8	# See shell/linters.sh for why each of these exists.
9	set -gx RUFF_OUTPUT_FORMAT concise
10	
...

#14 matchedBy=fts+vector agent-linters/website/index.html:27-57
source:
27	<meta property="og:image" content="https://cocodedk.github.io/agent-linters/og.png" />
28	<meta property="og:image:width" content="1200" />
29	<meta property="og:image:height" content="630" />
30	<meta property="og:image:alt" content="Two rulers on bone paper: a long ochre one marked 31 lines, a short blue one marked 5 lines, beside the name agent-linte...
31	<meta property="og:locale" content="en_US" />
32	<meta property="og:locale:alternate" content="fa_IR" />
33	
34	<meta name="twitter:card" content="summary_large_image" />
35	<meta name="twitter:title" content="agent-linters: linter output your coding agent can afford" />
36	<meta name="twitter:description" content="ruff and mypy spend 31 lines on three findings. lintp spends 5. One imperative line per finding, for Python, JS/TS, C...
...

#15 matchedBy=fts+vector agent-linters/bin/lintp:193-250
source:
193	def roots_of(paths):
194	    """Directories a linter's relative paths could be relative to."""
195	    seen = []
196	    for p in paths:
197	        root = p if os.path.isdir(p) else (os.path.dirname(p) or ".")
198	        if root not in seen:
199	            seen.append(root)
200	    return seen
201	
202	
...

#16 matchedBy=fts+vector message-test-plugin/CONTRIBUTING.md:77-88
heading: Changing the scripts
heading_level: 2
scope: Contributing to message-test
source:
77	## Changing the scripts
78	
79	`extract.py` and `cloze.py` are invoked by path from the skills. `scripts/validate-plugin.py`
80	checks that every `${CLAUDE_PLUGIN_ROOT}/...` path referenced in a skill still exists — a
81	rename would otherwise break the pipeline at runtime with no warning.
82	
83	Both are pure standard library. Keep them that way; the plugin has no install step, and a pip
84	dependency would introduce one. The only external requirement is the `pdftotext` binary, and
85	it is already guarded with `shutil.which` and a clean error message.
86	
...

#17 matchedBy=fts+vector agent-linters/bin/lintp:143-203
source:
143	    words = CAMEL.sub(" ", rule).lower().split()
144	    if not words:
145	        return None
146	    head, rest = words[0], " ".join(words[1:])
147	    if head == "no" and rest:
148	        return f"avoid {rest}"
149	    if head == "use" and rest:
150	        return f"use {rest}"
151	    return " ".join(words)
152	
...

#18 matchedBy=fts+vector agent-linters/README.md:33-64
heading: Install
heading_level: 2
scope: agent-linters
source:
33	## Install
34	
35	The linters themselves are not bundled:
36	
37	```sh
38	uv tool install ruff && uv tool install mypy      # Python
39	npm install -g oxlint @biomejs/biome              # JS/TS, CSS/JSON
40	```
41	
42	Then:
...

#19 matchedBy=fts+vector agent-linters/bin/lintp:356-400
source:
356	    for item in items:
357	        path = item.get("filename", "?")
358	        if not owns(path, JS_EXT):
359	            continue
360	        match = OXLINT_CODE.match(item.get("code", ""))
361	        rule = match["rule"] if match else item.get("code", "?")
362	        labels = item.get("labels") or [{}]
363	        line = labels[0].get("span", {}).get("line", 1)
364	        out.append((resolve(path, roots), line,
365	                    phrase(OXLINT_RULES, rule, item.get("message", "")), rule, False))
...

#20 matchedBy=fts+vector agent-linters/CONTRIBUTING.md:62-81
heading: The most valuable contribution: a new rule phrasing
heading_level: 2
scope: Contributing to agent-linters
source:
62	## The most valuable contribution: a new rule phrasing
63	
64	`bin/lintp` turns linter output into imperative instructions by looking a
65	rule code up in one of four tables: `RUFF_RULES`, `MYPY_RULES`, `OXLINT_RULES`,
66	`BIOME_RULES`. Each entry maps a rule code to a `(regex, template)` pair (or a
67	list of them, tried in order) that extracts the useful bits of the linter's
68	own message and rephrases them as an instruction — e.g. `F401` → "remove
69	unused import `os`", or `jsx-key` → "add a `key` prop to the list element".
70	
71	Adding an entry for a rule code you hit often is the easiest way to make this
...
