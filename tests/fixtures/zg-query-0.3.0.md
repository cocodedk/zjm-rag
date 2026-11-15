#1 code/__init__.py:1-9
1	"""zjm_rag: named lockers; zg finds, Jev ranks, an LLM answers."""

#2 code/search.py:118-126
118	def find(query, lockers, keys=None, *, limit=8, file_types=None, min_score=0.5, sort=None, rank=None,

#3 code/sealed.py:38-47
38	def locker_kind(cfg, name):

#4 code/lockers.py:113-126
113	def locker_list(*, config=None, runner=None, jev=None):

#5 code/core.py:9-13
9	def _locker_count(lockers_dir):

#6 code/cli.py:95-130
95	def _args_to_body(cmd, args):

#7 specs/06-lockers.md:3-14
heading: Goal
heading_level: 2
scope: 06 — Lockers: named indexes with files added and removed
3	## Goal

#8 code/files.py:101-124
101	def file_remove(locker, names, key=None, *, config=None, runner=zg.run, jev=None):

#9 code/search.py:129-153
129	def ask(query, lockers, keys=None, *, limit=8, file_types=None, min_score=0.5, sort=None, rank=None, top_k=3,

#10 code/zg.py:31-41
31	def parse(out, limit=8):

#11 specs/08-locker-keys.md:149-180
heading: Amendment: encryption is optional per locker (owner, 2026-09-26)
heading_level: 2
scope: 08 — Every locker encrypted with its own key, supplied by the app
149	## Amendment: encryption is optional per locker (owner, 2026-09-26)

#12 code/cli_human.py:4-39
4	def human(cmd, r):

#13 specs/01-library.md:94-106
heading: `ask(query, *, store=DEFAULT_STORE, top_k=3, answer_language=None, llm_command=None, runner=..., jev=..., **find_kwargs) -> dict`
heading_level: 3
scope: 01 — `zjm_rag` library: index, find, rank, ask::Behaviour
94	### `ask(query, *, store=DEFAULT_STORE, top_k=3, answer_language=None, llm_command=None, runner=..., jev=..., **find_kwargs) -> dict`

#14 specs/07-container.md:72-75
heading: Shared lock for reads (spec 06 gap)
heading_level: 3
scope: 07 — zjm runs only in a container::Behaviour
72	### Shared lock for reads (spec 06 gap)

#15 code/__main__.py:1-3
1	from .cli import main

#16 code/lockers.py:83-86
83	def locker_dir(cfg, name):

#17 office/kontor.md:1-5
heading: Kontoret i Aarhus
heading_level: 1
1	# Kontoret i Aarhus

#18 code/sealed.py:117-159
symbol: [function] open_locker
117	@contextmanager

#19 specs/03-http.md:11-33
heading: Behaviour
heading_level: 2
scope: 03 — local HTTP JSON API: `zjm serve`
11	## Behaviour

#20 code/config.py:103-136
103	def load(path=None, *, cwd=None, environ=None):

#21 office/kontor-oslo.md:1-5
heading: Kontoret i Oslo
heading_level: 1
1	# Kontoret i Oslo

#22 specs/04-mcp-install.md:84-96
heading: Jev request shape (pinned)
heading_level: 2
scope: 04 — MCP server and one-shot install
84	## Jev request shape (pinned)

#23 specs/02-cli.md:57-69
heading: Jev request shape (pinned)
heading_level: 2
scope: 02 — `zjm` command line with `--json`
57	## Jev request shape (pinned)

#24 specs/06-lockers.md:75-123
heading: Rules
heading_level: 3
scope: 06 — Lockers: named indexes with files added and removed::Behaviour
95	same way. The manifest

#25 code/jev.py:18-34
18	def post(payload, *, timeout=30):

#26 code/core.py:16-27
16	def doctor(*, config=None, runner=None, jev=None):

#27 office/buero.md:1-5
heading: Das Büro in Hamburg
heading_level: 1
1	# Das Büro in Hamburg

#28 specs/05-config-safety.md:209-220
heading: Jev request shape (pinned)
heading_level: 2
scope: 05 — Config file and safety floor
209	## Jev request shape (pinned)

#29 office/kontor-stockholm.md:1-5
heading: Kontoret i Stockholm
heading_level: 1
1	# Kontoret i Stockholm

#30 code/files.py:75-80
75	def file_add(locker, paths, key=None, *, config=None, runner=zg.run, jev=None):

#31 code/cli_keys.py:23-31
23	def add_to_body(cmd, key_file, body):

#32 code/ops.py:79-104
79	def _type_ok(value, spec):

#33 specs/08-locker-keys.md:26-52
heading: A sealed session: `zjm_rag/sealed.py`
heading_level: 3
scope: 08 — Every locker encrypted with its own key, supplied by the app::Behaviour
26	### A sealed session: `zjm_rag/sealed.py`

#34 code/mcp.py:27-93
27	def serve(stdin, stdout, *, config=None, runner=None, jev=None):

#35 code/copying.py:52-74
52	def _walk(src, dest, config, files, count_excluded, root=None):

#36 code/search.py:76-90
76	def _interleave(per_locker, limit):

#37 code/cli.py:20-92
symbol: [function] _parser
71	p.add_argument("-l", "--locker", action="append", dest="lockers", required=True, metavar="LOCKER")

#38 code/lockers.py:89-91
89	def _locations(cfg, name):

#39 code/keys.py:10-17
10	def check_key(key):

#40 code/http.py:25-121
symbol: [function] make_server
55	d"})
