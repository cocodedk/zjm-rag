# Security Policy

## What this is

`zjm-rag` is a local tool: it indexes folders you choose into a local store, searches them with
[zg](https://www.npmjs.com/package/@zvec/zvec-grep), asks Jev (the OpenRouter Decisions API) which files hold
the answer, and can pass those files to an OpenRouter model for an answer. It is
stdlib-only Python with no third-party runtime dependency.

## Actual threat surface

- **File content leaves the machine.** Ranking sends the question and each candidate file's full
  matched chunks to OpenRouter; answering sends up to 200,000 characters of the top accepted files
  to an OpenRouter model (`deepseek/deepseek-v4-flash` by default). Index only folders whose
  content you are willing to send.
  The planned `index()` copy (docs/lean/01) skips `.env*` files, `.git`, `node_modules` and
  `.venv`; other secrets in the indexed folders are not detected.
- **`OPENROUTER_API_KEY`** is read from the environment and sent only to `openrouter.ai`. Error
  messages must never echo the key or the response body; a change that does is a vulnerability.
- **The planned HTTP server (`zjm serve`)** has no authentication and binds `127.0.0.1` by
  default. Anyone who can reach its port can read indexed content, so binding elsewhere is an
  explicit choice. A request that makes it read or write outside its configured store is a
  vulnerability.
- **Indexed text is untrusted.** Snippets and file content reach Jev and the LLM as data; a file
  that steers the ranking or the answer through prompt injection is a known limit, and a report
  that it can make the tool act beyond answering is in scope.

## Out of scope

Vulnerabilities in zg, OpenRouter, Jev or the LLM client themselves belong with those projects.

## Reporting a vulnerability

Do **not** open a public GitHub issue for a security vulnerability. Instead:

- use the **"Report a vulnerability"** button on this repository's Security tab (a private
  advisory), or
- email **babak@cocode.dk** with a description and, if possible, the smallest reproduction.

Expect an acknowledgement within 5 business days and a fix within 30 days of confirmation. This
is a small project by [Cocode](https://cocode.dk), not a funded security team, and there is no
bug bounty.

## Supported versions

| Version | Supported |
|---------|-----------|
| latest `main` | ✅ |
| older   | ❌ |
