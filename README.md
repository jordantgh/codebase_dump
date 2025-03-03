# Codebase Dump

A Python utility for compiling a codebase into a single Markdown file for documentation, analysis, or sharing.

## Features

- Consolidates multiple source files into one Markdown document
- Includes folder structure visualisation
- Respects `.gitignore` patterns
- Built-in project type presets for common stacks (Python, JavaScript, ML, etc.)
- Handles binary files appropriately
- Multi-threaded processing for performance

## Requirements

- Python 3.12+
- Dependencies:
  - pathspec (for .gitignore processing)
  - rich (for CLI output)
  - click (for CLI interface)

## Overview

This tool is useful for creating comprehensive snapshots of your codebase for:

- Documentation
- Code review
- Analysis with AI assistants
- Preservation of project states

The output is a Markdown file with the complete folder structure and syntax-highlighted code snippets for all included files.