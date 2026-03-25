#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pathspec",
#     "rich",
# ]
# ///
"""Compile repository files into a single markdown document."""

import os
import argparse
from pathlib import Path, PurePosixPath
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import pathspec
import fnmatch
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.logging import RichHandler

# ---------------------------------------------------------------------------
# Logging & console
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
log = logging.getLogger("repo2md")
console = Console()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Known filenames → code-fence language hints
FILENAME_LANG: dict[str, str] = {
    "Makefile": "make",
    "GNUmakefile": "make",
    "Dockerfile": "dockerfile",
    "Containerfile": "dockerfile",
    "Vagrantfile": "ruby",
    "Gemfile": "ruby",
    "Rakefile": "ruby",
    "Justfile": "just",
    "Procfile": "yaml",
    "Brewfile": "ruby",
    "Snakefile": "python",
    "SConstruct": "python",
    "SConscript": "python",
    "BUILD": "python",
    "WORKSPACE": "python",
    ".gitignore": "gitignore",
    ".gitattributes": "gitattributes",
    ".gitmodules": "ini",
    ".dockerignore": "gitignore",
    ".editorconfig": "ini",
    ".env": "bash",
    ".env.example": "bash",
    ".env.local": "bash",
    ".bashrc": "bash",
    ".bash_profile": "bash",
    ".zshrc": "zsh",
    ".profile": "bash",
    "LICENSE": "text",
    "LICENCE": "text",
    "COPYING": "text",
    "AUTHORS": "text",
    "CHANGELOG": "text",
}

# Extension → code-fence language (where they differ from the extension itself)
EXT_LANG: dict[str, str] = {
    "py": "python",
    "pyi": "python",
    "js": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "ts": "typescript",
    "rs": "rust",
    "rb": "ruby",
    "yml": "yaml",
    "md": "markdown",
    "mdx": "markdown",
    "sh": "bash",
    "h": "c",
    "hpp": "cpp",
    "hxx": "cpp",
    "cc": "cpp",
    "cxx": "cpp",
    "kt": "kotlin",
    "kts": "kotlin",
    "m": "objectivec",
    "pl": "perl",
    "pm": "perl",
    "r": "r",
    "rmd": "rmarkdown",
    "ex": "elixir",
    "exs": "elixir",
    "hs": "haskell",
    "ml": "ocaml",
    "mli": "ocaml",
    "fs": "fsharp",
    "fsx": "fsharp",
    "tf": "hcl",
    "gradle": "groovy",
    "cfg": "ini",
    "conf": "ini",
    "txt": "text",
    "rst": "rst",
    "lock": "text",
}

PROJECT_PRESETS: dict[str, dict] = {
    "python": {
        "extensions": [
            "py", "pyi",
            "toml", "ini", "cfg", "yml", "yaml",
            "txt", "md", "rst",
            "dockerfile", "gitignore",
        ],
        "exclude_folders": [
            "venv", ".venv", "env", ".env",
            "__pycache__", ".pytest_cache",
            "build", "dist", "*.egg-info",
            ".tox", ".mypy_cache", ".coverage", "htmlcov",
            ".git", ".idea", ".vscode",
        ],
    },
    "js": {
        "extensions": [
            "js", "jsx", "ts", "tsx", "vue", "svelte",
            "json", "jsonc", "html", "css", "scss", "sass", "less",
            "mjs", "cjs", "md", "mdx", "lock", "gitignore",
        ],
        "exclude_folders": [
            "node_modules", "dist", "build", "coverage",
            ".next", ".nuxt", ".cache", ".parcel-cache",
            ".git", ".idea", ".vscode",
        ],
    },
    "lowlevel": {
        "extensions": [
            "c", "h", "cpp", "hpp", "cc", "cxx",
            "asm", "s", "rs", "go", "zig",
            "mk", "makefile", "cmake",
            "txt", "md", "gitignore",
        ],
        "exclude_folders": [
            "build", "bin", "obj", "target",
            "debug", "release", "deps",
            ".git", ".idea", ".vscode",
        ],
    },
    "ml": {
        "extensions": [
            "py", "yaml", "yml", "json",
            "txt", "md", "rst",
            "dockerfile", "cfg", "gitignore",
        ],
        "exclude_folders": [
            "venv", ".venv", "__pycache__",
            "data", "datasets", "checkpoints",
            "runs", "logs", "tensorboard", "wandb", "mlruns", "models",
            ".git", ".idea", ".vscode",
        ],
    },
    "datascience": {
        "extensions": [
            "py", "r", "rmd", "sql",
            "yaml", "yml", "txt", "md",
            "dockerfile", "gitignore",
        ],
        "exclude_folders": [
            "venv", ".venv", "__pycache__",
            "data", "raw_data", "processed_data",
            "interim", "external", "figures", "results", "outputs",
            ".git", ".idea", ".vscode",
        ],
    },
    "web": {
        "extensions": [
            "html", "htm", "css", "scss", "sass", "less",
            "js", "ts", "jsx", "tsx", "php", "rb", "erb",
            "json", "md", "svg", "xml", "webmanifest", "gitignore",
        ],
        "exclude_folders": [
            "node_modules", "vendor", "dist", "build",
            "public/assets", "tmp", "cache", ".sass-cache",
            ".git", ".idea", ".vscode",
        ],
    },
    "devops": {
        "extensions": [
            "yml", "yaml", "tf", "hcl",
            "dockerfile", "conf", "sh", "bash",
            "json", "toml", "ini", "env",
            "md", "txt", "gitignore",
        ],
        "exclude_folders": [
            ".terraform", "terraform.tfstate.d",
            "charts", "manifests", "secrets", "keys", "certs", "logs",
            ".git", ".idea", ".vscode",
        ],
    },
    "mobile": {
        "extensions": [
            "kt", "java", "xml", "gradle",
            "swift", "m", "h", "plist",
            "dart", "yaml", "json", "md", "gitignore",
        ],
        "exclude_folders": [
            "build", ".gradle", ".idea",
            "Pods", "DerivedData", ".dart_tool",
            "ios/Pods", ".git", ".vscode",
        ],
    },
    "fullstack_js_python": {
        "extensions": [
            "js", "jsx", "ts", "tsx", "vue", "svelte",
            "css", "scss", "sass", "less", "html",
            "json", "jsonc", "svg", "mjs", "cjs", "mdx", "lock",
            "py", "pyi", "toml", "ini", "cfg", "rst",
            "yml", "yaml", "md", "txt",
            "dockerfile", "env", "gitignore", "webmanifest",
        ],
        "exclude_folders": [
            "node_modules", "build", "dist",
            ".next", ".nuxt", ".cache", ".parcel-cache", "coverage",
            "venv", ".venv", "__pycache__", "*.egg-info",
            ".pytest_cache", ".tox", ".mypy_cache", ".coverage", "htmlcov",
            ".git", ".idea", ".vscode",
        ],
    },
    "fullstack_mobile": {
        "extensions": [
            "kt", "java", "xml", "gradle",
            "swift", "m", "h", "plist", "dart",
            "py", "go", "rs", "js", "ts", "php", "rb",
            "yml", "yaml", "json", "md", "txt",
            "dockerfile", "gitignore",
        ],
        "exclude_folders": [
            "build", ".gradle", ".idea",
            "Pods", "DerivedData", ".dart_tool", "ios/Pods",
            "venv", ".venv", "__pycache__",
            "target", "node_modules", "vendor",
            ".git", ".vscode",
        ],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_size(n_bytes: int) -> str:
    """Format byte count as human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024:
            return f"{n_bytes} {unit}" if unit == "B" else f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} TB"


def _relative_path(filepath: Path, base: Path) -> Path:
    """Compute relative path, handling paths not under base via os.path.relpath."""
    try:
        return filepath.resolve().relative_to(base.resolve())
    except ValueError:
        return Path(os.path.relpath(filepath.resolve(), base.resolve()))


def _detect_language(filepath: Path, content: str) -> str:
    """Determine code-fence language for a file."""
    # Known filename
    if filepath.name in FILENAME_LANG:
        return FILENAME_LANG[filepath.name]

    # Extension
    ext = filepath.suffix[1:].lower() if filepath.suffix else ""
    if ext:
        return EXT_LANG.get(ext, ext)

    # Shebang for extensionless files
    first_line = content.split("\n", 1)[0] if content else ""
    if first_line.startswith("#!"):
        shebang = first_line.lower()
        if "python" in shebang:
            return "python"
        if "bash" in shebang or "/sh" in shebang:
            return "bash"
        if "node" in shebang:
            return "javascript"
        if "ruby" in shebang:
            return "ruby"
        if "perl" in shebang:
            return "perl"
        if "fish" in shebang:
            return "fish"

    return "text"


def _matches_pattern(filepath: Path, rel_path: str, pattern: str) -> bool:
    """Check if a file matches a name or path pattern.

    If the pattern contains '/', it's matched against the relative path using
    PurePosixPath.match() (supports ** for recursive globbing).
    Otherwise, it's matched against the filename using fnmatch.
    """
    norm_pattern = pattern.replace(os.sep, "/")
    if norm_pattern.startswith("./"):
        norm_pattern = norm_pattern[2:]

    if "/" in norm_pattern:
        norm_rel = rel_path.replace(os.sep, "/")
        if norm_rel.startswith("./"):
            norm_rel = norm_rel[2:]
        return PurePosixPath(norm_rel).match(norm_pattern)
    else:
        return fnmatch.fnmatch(filepath.name, norm_pattern)


def _dir_matches_pattern(dir_name: str, rel_dir: str, pattern: str) -> bool:
    """Check if a directory matches a name or path pattern."""
    norm_pattern = pattern.replace(os.sep, "/")
    if norm_pattern.startswith("./"):
        norm_pattern = norm_pattern[2:]

    if "/" in norm_pattern:
        norm_rel = rel_dir.replace(os.sep, "/")
        if norm_rel.startswith("./"):
            norm_rel = norm_rel[2:]
        return PurePosixPath(norm_rel).match(norm_pattern)
    else:
        return fnmatch.fnmatch(dir_name, norm_pattern)


# ---------------------------------------------------------------------------
# Gitignore
# ---------------------------------------------------------------------------


def load_gitignore(folders: list[Path]) -> pathspec.PathSpec | None:
    """Load and combine .gitignore patterns from the given folders."""
    patterns: list[str] = []
    for folder in folders:
        gitignore = folder.resolve() / ".gitignore"
        if gitignore.is_file():
            try:
                patterns.extend(gitignore.read_text(encoding="utf-8").splitlines())
            except Exception as e:
                log.warning(f"Could not read {gitignore}: {e}")
    if not patterns:
        return None
    try:
        return pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern, patterns
        )
    except Exception as e:
        log.error(f"Error parsing .gitignore patterns: {e}")
        return None


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def _should_exclude_dir(
    dir_path: Path, dir_name: str, base: Path, opts: dict
) -> bool:
    """Decide whether a directory should be pruned from the walk."""
    resolved = dir_path.resolve()

    # Hidden directories
    if not opts.get("include_hidden", False) and dir_name.startswith("."):
        return True

    # Resolved-path match
    if resolved in opts.get("exclude_folders_resolved", set()):
        return True

    # Bare-name match (matches at any depth, e.g. "node_modules")
    if dir_name in opts.get("exclude_folder_names", set()):
        return True

    # Glob/path pattern match
    try:
        rel_dir = str(dir_path.resolve().relative_to(base.resolve()))
    except ValueError:
        rel_dir = dir_name

    for pattern in opts.get("exclude_folder_patterns", []):
        if _dir_matches_pattern(dir_name, rel_dir, pattern):
            return True

    # Gitignore directory match (trailing slash convention)
    spec = opts.get("gitignore_spec")
    if spec:
        rel_posix = rel_dir.replace(os.sep, "/") + "/"
        if spec.match_file(rel_posix):
            return True

    return False


def should_include_file(filepath: Path, rel_path: str, opts: dict) -> bool:
    """Centralised decision on whether to include a file."""
    resolved = filepath.resolve()

    # Always skip the output file
    if opts.get("output_resolved") and resolved == opts["output_resolved"]:
        return False

    # Directly specified files bypass everything else
    if resolved in opts.get("direct_files", set()):
        return True

    # Hidden file/directory check (on the relative path components)
    if not opts.get("include_hidden", False):
        parts = Path(rel_path).parts
        if any(p.startswith(".") for p in parts):
            return False

    # --- Explicit inclusion (bypasses extension filter) ---
    explicitly_included = False
    for pattern in opts.get("include", []):
        if _matches_pattern(filepath, rel_path, pattern):
            explicitly_included = True
            break

    # --- Exclusion checks (override explicit inclusion) ---
    # Resolved-path exclusion
    if resolved in opts.get("exclude_files_resolved", set()):
        return False

    # Pattern exclusion
    for pattern in opts.get("exclude", []):
        if _matches_pattern(filepath, rel_path, pattern):
            return False

    # Gitignore
    spec = opts.get("gitignore_spec")
    if spec:
        rel_posix = rel_path.replace(os.sep, "/")
        if spec.match_file(rel_posix):
            return False

    # --- Extension filtering (skipped for explicitly-included files) ---
    if not explicitly_included:
        ext = filepath.suffix[1:].lower() if filepath.suffix else ""

        # Excluded extensions
        if ext and ext in opts.get("exclude_extensions", set()):
            return False

        # When extension filtering is active, only allowed extensions pass
        if opts.get("extension_filter_active", False):
            if ext:
                if ext not in opts.get("extensions", set()):
                    return False
            else:
                # Extensionless file — needs explicit opt-in
                if not opts.get("include_extensionless", False):
                    return False
        # When extension filtering is OFF, everything passes (including
        # extensionless files) — this is the default when no -e / --ptype

    # --- File size check ---
    max_size = opts.get("max_file_size")
    if max_size:
        try:
            size = filepath.stat().st_size
            if size > max_size:
                log.info(
                    f"Skipping (>{_format_size(max_size)}): {rel_path} "
                    f"({_format_size(size)})"
                )
                return False
        except OSError:
            pass

    return True


# ---------------------------------------------------------------------------
# File-list builder
# ---------------------------------------------------------------------------


def build_file_list(
    base_folders: list[Path], opts: dict
) -> tuple[list[Path], dict[Path, Path]]:
    """Walk directories and collect files, returning (sorted_files, file→base map)."""
    found: dict[Path, Path] = {}  # resolved_path → base_folder

    for base in base_folders:
        resolved_base = base.resolve()

        for root, dirs, files in os.walk(resolved_base, topdown=True):
            root_path = Path(root).resolve()

            # Prune excluded directories in-place
            dirs[:] = [
                d
                for d in dirs
                if not _should_exclude_dir(root_path / d, d, resolved_base, opts)
            ]

            for filename in files:
                filepath = root_path / filename
                resolved = filepath.resolve()
                if resolved in found:
                    continue

                try:
                    rel_path = str(filepath.relative_to(resolved_base))
                except ValueError:
                    continue

                if should_include_file(filepath, rel_path, opts):
                    found[resolved] = resolved_base

    # Direct files are always added (output-file guard is inside should_include_file)
    for f in opts.get("direct_file_paths", []):
        resolved = f.resolve()
        if resolved not in found:
            # Use CWD as the base so the display path is the user-supplied path
            found[resolved] = Path.cwd()

    return sorted(found), found


# ---------------------------------------------------------------------------
# Display paths & tree
# ---------------------------------------------------------------------------


def _compute_display_paths(
    files: list[Path],
    file_to_base: dict[Path, Path],
    multi_base: bool,
) -> dict[Path, Path]:
    """Map resolved file paths to human-readable display paths."""
    result: dict[Path, Path] = {}
    for f in files:
        base = file_to_base[f]
        rel = _relative_path(f, base)
        if multi_base:
            rel = Path(base.name) / rel
        result[f] = rel
    return result


def format_tree(display_paths: list[Path], root_label: str) -> str:
    """Build an ASCII tree from a sorted list of relative display paths."""
    # Build nested dict: directories → dict, files → None
    tree: dict = {}
    for dp in sorted(display_paths):
        node = tree
        parts = dp.parts
        for part in parts[:-1]:
            if part not in node or node[part] is None:
                node[part] = {}
            node = node[part]
        node[parts[-1]] = None  # leaf

    lines = [f"{root_label}/"]
    lines.extend(_render_tree(tree, prefix=""))
    return "\n".join(lines)


def _render_tree(tree: dict, prefix: str) -> list[str]:
    """Recursively render tree dict as lines with box-drawing connectors."""
    lines: list[str] = []
    # Directories first, then files, both alphabetical
    entries = sorted(tree.items(), key=lambda x: (x[1] is None, x[0].lower()))
    for i, (name, subtree) in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        extension = "    " if is_last else "│   "
        if subtree is not None:
            lines.append(f"{prefix}{connector}{name}/")
            lines.extend(_render_tree(subtree, prefix + extension))
        else:
            lines.append(f"{prefix}{connector}{name}")
    return lines


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------


def process_file(filepath: Path, display_path: Path) -> tuple[Path, str] | None:
    """Read a single file, returning (display_path, formatted_markdown) or None."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        log.info(f"Binary file: {display_path}")
        return (
            display_path,
            f"## `{display_path}`\n\n*Binary file — content not shown.*\n\n",
        )
    except Exception as e:
        log.error(f"Error reading {display_path}: {e}")
        return None

    lang = _detect_language(filepath, content)
    body = content.strip()
    return (
        display_path,
        f"## `{display_path}`\n\n```{lang}\n{body}\n```\n\n",
    )


# ---------------------------------------------------------------------------
# Argument parsing helpers
# ---------------------------------------------------------------------------


def _dir_path(value: str) -> Path:
    """Argparse type: verify directory exists."""
    p = Path(value)
    if not p.exists():
        raise argparse.ArgumentTypeError(f"'{value}' does not exist.")
    if not p.is_dir():
        raise argparse.ArgumentTypeError(f"'{value}' is not a directory.")
    return p


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile repository files into a single markdown document.",
        epilog=(
            "Preset types: " + ", ".join(PROJECT_PRESETS) + "\n\n"
            "Examples:\n"
            "  %(prog)s -f ./src                          # all text files in src/\n"
            "  %(prog)s -f ./src -e py js                  # only .py and .js\n"
            "  %(prog)s --files Makefile Dockerfile         # just those two files\n"
            "  %(prog)s -f . --include 'Makefile' -e py     # .py files + any Makefile\n"
            "  %(prog)s -f . --ptype python --dry-run       # preview python preset\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # -- Input/output --
    io_group = parser.add_argument_group("Input / Output")
    io_group.add_argument(
        "-f", "--folders",
        nargs="+", type=_dir_path, default=[],
        metavar="DIR",
        help="Folders to scan recursively. Defaults to '.' when neither -f nor --files is given.",
    )
    io_group.add_argument(
        "--files",
        nargs="+", type=Path, default=[],
        metavar="FILE",
        help="Individual files to include unconditionally (bypasses all filtering).",
    )
    io_group.add_argument(
        "-o", "--output",
        default="codebase.md", metavar="FILE",
        help="Output markdown file (default: codebase.md).",
    )

    # -- Presets --
    parser.add_argument(
        "--ptype",
        choices=list(PROJECT_PRESETS), nargs="+",
        metavar="PRESET",
        help="Project-type preset(s) for extension/folder filtering.",
    )

    # -- Extension filtering --
    ext_group = parser.add_argument_group("Extension filtering")
    ext_group.add_argument(
        "-e", "--extensions",
        nargs="+", default=[], metavar="EXT",
        help=(
            "Activate extension filtering; include only these extensions "
            "(e.g. py js ts). Adds to preset extensions if --ptype is also given."
        ),
    )
    ext_group.add_argument(
        "--exclude-extensions",
        nargs="+", default=[], metavar="EXT",
        help="Exclude these extensions regardless of other settings.",
    )
    ext_group.add_argument(
        "--include-extensionless",
        action="store_true",
        help=(
            "When extension filtering is active (-e / --ptype), also include "
            "files that have no extension (e.g. Makefile, LICENSE). "
            "Has no effect when extension filtering is off."
        ),
    )

    # -- Include / exclude patterns --
    pat_group = parser.add_argument_group(
        "Include / Exclude patterns",
        description=(
            "Patterns containing '/' are matched against the path relative to "
            "the scanned folder (supports ** for recursive matching). "
            "Patterns without '/' are matched against the filename only."
        ),
    )
    pat_group.add_argument(
        "--include",
        nargs="+", default=[], metavar="PATTERN",
        help=(
            "Include files matching these patterns, bypassing extension filtering. "
            "E.g. 'Makefile', '*.test.js', 'src/**/*.proto'."
        ),
    )
    pat_group.add_argument(
        "--exclude",
        nargs="+", default=[], metavar="PATTERN",
        help=(
            "Exclude files matching these patterns (applied after includes). "
            "E.g. '*.log', 'docs/*', '**/generated/**'."
        ),
    )
    pat_group.add_argument(
        "--exclude-folders",
        nargs="+", default=[], metavar="NAME",
        help=(
            "Exclude directories by name or glob (e.g. node_modules, '*_cache'). "
            "Adds to preset exclusions if --ptype is also given."
        ),
    )

    # -- Behaviour --
    beh_group = parser.add_argument_group("Behaviour")
    beh_group.add_argument(
        "--no-gitignore", action="store_true",
        help="Do not respect .gitignore files.",
    )
    beh_group.add_argument(
        "--include-hidden", action="store_true",
        help="Include hidden files and directories (those starting with '.').",
    )
    beh_group.add_argument(
        "--max-file-size",
        type=int, default=0, metavar="KB",
        help="Skip files larger than this many KB. 0 = no limit (default).",
    )
    beh_group.add_argument(
        "--dry-run", action="store_true",
        help="List files that would be included, without writing the output.",
    )
    beh_group.add_argument(
        "-v", "--verbose", action="store_true",
        help="Debug-level logging.",
    )

    args = parser.parse_args()
    log.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    # ---- Resolve base folders ----
    base_folders: list[Path] = args.folders
    if not base_folders and not args.files:
        base_folders = [Path(".")]

    # ---- Validate & resolve direct files ----
    direct_files: set[Path] = set()
    direct_file_paths: list[Path] = []
    for f in args.files:
        if f.is_file():
            direct_files.add(f.resolve())
            direct_file_paths.append(f)
        else:
            console.print(f"[yellow]Warning: file not found: {f}[/]")

    output_path = Path(args.output)
    output_resolved = output_path.resolve()

    # ---- Extension filtering ----
    user_extensions: set[str] = {ext.lower().lstrip(".") for ext in args.extensions}
    exclude_extensions: set[str] = {
        ext.lower().lstrip(".") for ext in args.exclude_extensions
    }

    # Merge preset extensions
    preset_extensions: set[str] = set()
    preset_exclude_folders_raw: list[str] = []
    if args.ptype:
        for ptype in args.ptype:
            preset = PROJECT_PRESETS.get(ptype, {})
            preset_extensions.update(preset.get("extensions", []))
            preset_exclude_folders_raw.extend(preset.get("exclude_folders", []))

    all_extensions = user_extensions | preset_extensions
    extension_filter_active = bool(all_extensions)

    # ---- Folder exclusions ----
    all_exclude_folders_raw = list(args.exclude_folders) + preset_exclude_folders_raw

    # Separate glob patterns from bare names
    exclude_folder_patterns: list[str] = []
    exclude_folder_names: set[str] = set()
    for entry in all_exclude_folders_raw:
        if any(c in entry for c in ("*", "?", "[")):
            exclude_folder_patterns.append(entry)
        else:
            exclude_folder_names.add(entry)

    # Resolve bare names relative to each base folder (for exact-path matching)
    exclude_folders_resolved: set[Path] = set()
    for base in base_folders:
        for name in exclude_folder_names:
            exclude_folders_resolved.add((base / name).resolve())

    # ---- File exclusions (from --exclude that look like specific paths) ----
    # We don't separate these here — _matches_pattern handles both name and
    # path patterns uniformly.  But we do pre-resolve any literal paths the
    # user passes via --exclude so we can compare resolved paths directly.
    exclude_files_resolved: set[Path] = set()
    for pattern in args.exclude:
        # If it looks like a literal path (no glob chars, contains /), resolve it
        if "/" in pattern and not any(c in pattern for c in ("*", "?", "[")):
            for base in base_folders:
                exclude_files_resolved.add((base / pattern).resolve())
            exclude_files_resolved.add(Path(pattern).resolve())

    # ---- Gitignore ----
    gitignore_spec = None
    if not args.no_gitignore:
        gitignore_spec = load_gitignore(base_folders)

    # ---- Max file size ----
    max_file_size = args.max_file_size * 1024 if args.max_file_size > 0 else None

    # ---- Build options dict ----
    opts: dict = {
        "output_resolved": output_resolved,
        "direct_files": direct_files,
        "direct_file_paths": direct_file_paths,
        "include_hidden": args.include_hidden,
        "include": args.include,
        "exclude": args.exclude,
        "exclude_files_resolved": exclude_files_resolved,
        "exclude_folders_resolved": exclude_folders_resolved,
        "exclude_folder_names": exclude_folder_names,
        "exclude_folder_patterns": exclude_folder_patterns,
        "gitignore_spec": gitignore_spec,
        "extension_filter_active": extension_filter_active,
        "extensions": all_extensions,
        "exclude_extensions": exclude_extensions,
        "include_extensionless": args.include_extensionless,
        "max_file_size": max_file_size,
    }

    # ---- Summary ----
    console.print("[bold blue]repo2md[/]")
    if base_folders:
        console.print(
            f"  Scanning: {', '.join(str(b) for b in base_folders)}"
        )
    if direct_file_paths:
        console.print(
            f"  Direct files: {', '.join(str(f) for f in direct_file_paths)}"
        )
    console.print(f"  Output: [green]{output_path}[/]")
    if extension_filter_active:
        console.print(
            f"  Extensions: [green]{', '.join(sorted(all_extensions))}[/]"
            + (" [cyan]+extensionless[/]" if args.include_extensionless else "")
        )
    else:
        console.print("  Extensions: [cyan]all (no filter)[/]")
    if exclude_extensions:
        console.print(
            f"  Excluding ext: [yellow]{', '.join(sorted(exclude_extensions))}[/]"
        )
    if all_exclude_folders_raw:
        console.print(
            f"  Excluding folders: [yellow]{', '.join(sorted(set(all_exclude_folders_raw)))}[/]"
        )
    if args.include:
        console.print(
            f"  Include patterns: [green]{', '.join(args.include)}[/]"
        )
    if args.exclude:
        console.print(
            f"  Exclude patterns: [yellow]{', '.join(args.exclude)}[/]"
        )
    gitignore_status = (
        "yes" if gitignore_spec else "yes (no patterns loaded)"
    ) if not args.no_gitignore else "no"
    console.print(f"  Gitignore: [cyan]{gitignore_status}[/]")
    console.print(
        f"  Hidden files: [cyan]{'yes' if args.include_hidden else 'no'}[/]"
    )
    if max_file_size:
        console.print(f"  Max file size: [cyan]{_format_size(max_file_size)}[/]")
    console.print()

    # ---- Build file list ----
    files_to_process, file_to_base = build_file_list(base_folders, opts)

    if not files_to_process:
        log.warning("No files matched. Nothing to do.")
        return

    multi_base = len(base_folders) > 1
    display_paths = _compute_display_paths(files_to_process, file_to_base, multi_base)

    # ---- Dry run ----
    if args.dry_run:
        total_size = 0
        for f in files_to_process:
            try:
                total_size += f.stat().st_size
            except OSError:
                pass
        console.print(
            f"[bold]{len(files_to_process)} files, "
            f"{_format_size(total_size)} total[/]\n"
        )
        for f in files_to_process:
            dp = display_paths[f]
            try:
                sz = _format_size(f.stat().st_size)
            except OSError:
                sz = "?"
            console.print(f"  {dp}  [dim]({sz})[/]")

        console.print()
        if len(base_folders) == 1:
            root_label = base_folders[0].resolve().name
        elif base_folders:
            root_label = "<multi>"
        else:
            root_label = "."
        console.print(
            format_tree(list(display_paths.values()), root_label)
        )
        return

    # ---- Write header & tree ----
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# Codebase: {output_path.stem}\n\n")
            f.write(
                f"Scanned: `{'`, `'.join(str(b) for b in base_folders)}`\n\n"
            )
            if direct_file_paths:
                f.write(
                    f"Direct files: `{'`, `'.join(str(p) for p in direct_file_paths)}`\n\n"
                )

        # Tree
        if len(base_folders) == 1:
            root_label = base_folders[0].resolve().name
        elif base_folders:
            root_label = "<multi>"
        else:
            root_label = "."

        tree_str = format_tree(list(display_paths.values()), root_label)
        with open(output_path, "a", encoding="utf-8") as f:
            f.write("## Structure\n\n```\n")
            f.write(tree_str)
            f.write("\n```\n\n---\n\n")
    except Exception as e:
        log.error(f"Failed writing header/tree: {e}")
        return

    # ---- Process files concurrently ----
    results: dict[Path, str] = {}  # display_path → formatted content
    skipped = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Reading files", total=len(files_to_process))

        with ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
            futures = {
                pool.submit(process_file, fp, display_paths[fp]): fp
                for fp in files_to_process
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        dp, content = result
                        results[dp] = content
                    else:
                        skipped += 1
                except Exception as e:
                    log.error(f"Error processing {futures[future]}: {e}")
                    skipped += 1
                finally:
                    progress.update(task, advance=1)

    # ---- Append content in sorted order ----
    try:
        with open(output_path, "a", encoding="utf-8") as f:
            for dp in sorted(results):
                f.write(results[dp])
    except Exception as e:
        log.error(f"Failed writing file contents: {e}")
        return

    console.print(
        f"\n[bold green]✓[/] {len(results)} files written to "
        f"[blue]{output_path}[/]. {skipped} skipped."
    )


if __name__ == "__main__":
    main()