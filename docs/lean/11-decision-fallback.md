# Decision model fallback

Reference: the installed jev-decisions skill’s SKILL.md and scripts/jev_schema.py,
with fallback semantics from scripts/jev_transport.py.

Use the four-model order documented in README, beginning with perplexity/pplx-decider-v1.1-27b.
Precedence: explicit model argument/CLI flag, request model, JEV_MODEL, default.
A listed model starts its remaining default suffix; an unlisted model gets one attempt.
Transport errors, invalid JSON, oversized responses, provider error objects and non-object
responses trigger fallback, never a valid low score; invalid decision values still fail ranking.
Keep redirects disabled, sanitize transport errors, cap requests at 512 KiB and responses at
1 MiB, and retain the 30-second per-attempt socket timeout.
Expose provider model identity as returned_model in find/ask and human output; absent identity
is null. Keep CLI, HTTP, MCP, library and container environment overrides consistent.

Acceptance: exactly **84 tests**, all offline with injected providers.
