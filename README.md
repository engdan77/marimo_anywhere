# 📒 Marimo Anywhere 🕸️

Marimo Anywhere is a small toolkit for "minifying" **Marimo** notebooks from the command line and scripts to allow sharing them easily and within limitations that exists share embedded/encoded code within URL.

## Motivation
It focuses on practical workflows like:

- Turning notebooks into portable artifacts (e.g., minified sources into standalone Python files or URLs)
- Driving notebook-related tasks in repeatable CLI commands
- Supporting automation use-cases (local runs, CI, and simple scripting)

This repository is intentionally lightweight and aims to provide composable utilities you can wire into your own workflow.

## Usage

```shell
$ uvx --from https://github.com/engdan77/marimo_anywhere.git marimo-anywhere --help
Usage: marimo-anywhere COMMAND

╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ minify-to-file  Minify a Marimo source file while preserving its behavior.                       │
│ minify-to-url   Minifies the given Marimo file to a reduced version based on the whitelist       │
│                 expression and converts it to a shareable Marimo URL.                            │
│ --help (-h)     Display this message and exit.                                                   │
│ --version       Display application version.                                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```