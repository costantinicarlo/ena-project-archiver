---
description: "Use when creating or editing Markdown files to preserve one-line prose paragraphs."
applyTo: "**/*.md"
---

# Markdown Text Wrapping

- Keep each prose paragraph on one logical source line, regardless of its rendered or editor width.
- Do not hard-wrap prose at a fixed column width.
- Keep each list item on one source line unless it contains a nested block, fenced code block, or another structure that requires multiple lines.
- Preserve intentional line breaks in fenced code blocks, tables, ASCII trees, frontmatter, and other whitespace-sensitive content.
- Before finishing a Markdown edit, inspect every changed prose paragraph and remove newline characters inserted only for visual wrapping.
