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
import fnmatch
from pathlib import Path
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import pathspec
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

# Directories that are never descended into, under any configuration.
# (Use --files to pull individual files out of these if you really must.)
ALWAYS_EXCLUDED_DIRS = {".git", ".hg", ".svn"}

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_size(n_bytes: float) -> str:
    """Format byte count as human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024:
            return f"{n_bytes:.0f} {unit}" if unit == "B" else f"{n_bytes:.1f} {unit}"
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
    if filepath.name in FILENAME_LANG:
        return FILENAME_LANG[filepath.name]

    ext = filepath.suffix[1:].lower() if filepath.suffix else ""
    if ext:
        return EXT_LANG.get(ext, ext)

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


def _compile_spec(
    patterns: list[str], flag_name: str, parser: argparse.ArgumentParser
) -> pathspec.PathSpec | None:
    """Compile gitignore-style patterns into a PathSpec, or exit on bad input."""
    if not patterns:
        return None
    try:
        return pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern, patterns
        )
    except Exception as e:
        parser.error(f"invalid pattern in {flag_name}: {e}")
        return None  # unreachable; keeps type-checkers happy


def _dir_could_contain_match(rel_dir_posix: str, include_patterns: list[str]) -> bool:
    """Heuristic: could a *path-qualified* include pattern match under this dir?

    Only patterns containing '/' are considered — bare-name patterns
    (e.g. '*.proto') deliberately do NOT unlock pruned (hidden/gitignored)
    directories, otherwise a broad include would drag in venvs, build
    output, etc.  Path-qualified patterns (e.g. '.github/**',
    'dist/bundle.js') unlock exactly the directories they name.

    This errs on the permissive side: returning True merely means "descend
    and let the file-level check decide".
    """
    dir_parts = rel_dir_posix.split("/")
    for raw in include_patterns:
        pat = raw.strip()
        if not pat or pat.startswith("!"):
            continue
        core = pat.lstrip("/").rstrip("/")
        if "/" not in core:
            continue  # bare-name pattern: doesn't unlock pruned dirs
        pat_parts = core.split("/")
        compatible = True
        for i, dpart in enumerate(dir_parts):
            if i >= len(pat_parts):
                # Pattern matched a parent of this dir → whole subtree eligible
                break
            ppart = pat_parts[i]
            if ppart == "**":
                break  # anything below could match
            if not fnmatch.fnmatch(dpart, ppart):
                compatible = False
                break
        if compatible:
            return True
    return False


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


def _should_exclude_dir(dir_path: Path, dir_name: str, base: Path, opts: dict) -> bool:
    """Decide whether a directory should be pruned from the walk.

    Precedence:
      1. VCS dirs (.git etc.)            → always pruned
      2. --exclude-folders / --exclude   → always pruned (excludes win)
      3. hidden dirs (no --include-hidden) and gitignored dirs
         → pruned, UNLESS a path-qualified --include pattern could
           match something inside them.
    """
    if dir_name in ALWAYS_EXCLUDED_DIRS:
        return True

    try:
        rel_posix = str(dir_path.resolve().relative_to(base)).replace(os.sep, "/")
    except ValueError:
        rel_posix = dir_name
    dir_posix = rel_posix + "/"

    # Hard exclusions — never re-entered, even by --include.
    spec = opts["exclude_dirs_spec"]
    if spec and spec.match_file(dir_posix):
        return True
    spec = opts["exclude_spec"]
    if spec and spec.match_file(dir_posix):
        return True

    include_patterns: list[str] = opts["include_patterns"]

    # Hidden directories
    if not opts["include_hidden"] and dir_name.startswith("."):
        if not (
            include_patterns
            and _dir_could_contain_match(rel_posix, include_patterns)
        ):
            return True

    # Gitignored directories
    spec = opts["gitignore_spec"]
    if spec and spec.match_file(dir_posix):
        if not (
            include_patterns
            and _dir_could_contain_match(rel_posix, include_patterns)
        ):
            return True

    return False


def should_include_file(filepath: Path, rel_path: str, opts: dict) -> bool:
    """Centralised decision on whether to include a file.

    Pipeline (see --help for the user-facing description):
      1. output file       → never included
      2. --files           → always included (bypasses everything below)
      3. hard excludes     → --exclude patterns, --exclude-extensions
      4. --include match   → included, bypassing hidden/gitignore/extension
                             filters (but still subject to step 3 and size)
      5. default filters   → hidden, gitignore, extension filter / whitelist
      6. --max-file-size
    """
    resolved = filepath.resolve()

    # 1. Never include the output file.
    if opts["output_resolved"] and resolved == opts["output_resolved"]:
        return False

    # 2. Directly specified files bypass everything else.
    if resolved in opts["direct_files"]:
        return True

    rel_posix = rel_path.replace(os.sep, "/")
    ext = filepath.suffix[1:].lower() if filepath.suffix else ""

    # 3. Hard excludes — these always win, including over --include.
    spec = opts["exclude_spec"]
    if spec and spec.match_file(rel_posix):
        return False
    if ext and ext in opts["exclude_extensions"]:
        return False

    # 4. Explicit includes.
    include_spec = opts["include_spec"]
    explicitly_included = bool(include_spec and include_spec.match_file(rel_posix))

    if not explicitly_included:
        # 5a. Hidden files / files inside hidden directories.
        if not opts["include_hidden"]:
            if any(p.startswith(".") for p in Path(rel_path).parts):
                return False

        # 5b. Gitignore.
        spec = opts["gitignore_spec"]
        if spec and spec.match_file(rel_posix):
            return False

        # 5c. Extension filter / whitelist semantics.
        if opts["extension_filter_active"]:
            if ext:
                if ext not in opts["extensions"]:
                    return False
            else:
                if not opts["include_extensionless"]:
                    return False
        elif include_spec:
            # --include given without -e: includes act as a whitelist,
            # so non-matching files are rejected.
            return False
        # Neither --include nor -e: everything passes (default).

    # 6. File size limit.
    max_size = opts["max_file_size"]
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
    for f in opts["direct_file_paths"]:
        resolved = f.resolve()
        if resolved not in found and resolved != opts["output_resolved"]:
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
        f"## `{display_path}`\n\n~~~{lang}\n{body}\n~~~\n\n",
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


EPILOG = """\
how filtering works
-------------------
Every file found while scanning -f/--folders passes through these stages,
in order. Earlier stages always win over later ones:

  1. The output file itself and VCS directories (.git, .hg, .svn) are
     always skipped.
  2. Hard excludes — always win, even over --include:
       --exclude patterns, --exclude-folders, --exclude-extensions.
       Directories removed by --exclude-folders are never descended into.
  3. Explicit includes — files matching an --include pattern are accepted,
     bypassing the hidden-file rule, .gitignore, and extension filtering.
  4. Default filters (only for files NOT matched by --include):
       - hidden files/directories are skipped unless --include-hidden
       - files matching .gitignore are skipped unless --no-gitignore
       - if -e/--extensions is given, only those extensions pass
         (extensionless files like Makefile additionally need
         --include-extensionless)
       - if --include is given but -e is NOT, only files matching the
         include patterns are taken (whitelist mode)
       - if neither --include nor -e is given, everything passes
  5. --max-file-size, if set.

Files passed via --files skip ALL of the above, including size limits.

combining --include and -e
--------------------------
  --include only      whitelist: only files matching the patterns
  -e only             only files with those extensions
  both                union: files matching either the patterns or
                      the extensions

pattern syntax
--------------
--include, --exclude and --exclude-folders use .gitignore-style patterns,
matched against paths relative to each scanned folder:

  *.proto           any .proto file, at any depth
  Makefile          any file named Makefile, at any depth
  src/**/*.ts       .ts files anywhere under src/
  docs              a file or directory named docs (and its contents),
                    at any depth
  /vendor           only the top-level vendor entry (leading / anchors)
  build/            directories named build (trailing / = dirs only)

traversal of pruned directories
-------------------------------
Hidden and gitignored directories are normally pruned without being
entered. A path-qualified --include pattern (one containing '/') unlocks
the directories it names, so these work as expected:

  --include '.github/**'        files inside a hidden directory
  --include 'dist/bundle.js'    a file inside a gitignored directory

Bare-name patterns (e.g. '*.py') deliberately do NOT unlock pruned
directories — otherwise they would drag in virtualenvs, build output, etc.
Directories pruned by --exclude-folders are never unlocked.

examples
--------
  %(prog)s
      Everything under ., respecting .gitignore.

  %(prog)s -f src tests -o code.md
      Scan two folders into code.md.

  %(prog)s -e py toml md
      Only .py, .toml and .md files.

  %(prog)s -e py --include Makefile Dockerfile
      .py files, plus any Makefile or Dockerfile.

  %(prog)s --include '*.py' 'src/**/*.sql'
      Whitelist mode: only files matching these patterns.

  %(prog)s --include 'src/**' --exclude 'src/generated/**'
      Everything under src/ except generated code.

  %(prog)s --include '.github/**'
      Reach into a hidden directory without --include-hidden.

  %(prog)s --files .env config/secrets.yaml
      Specific files, bypassing all filtering.

  %(prog)s --exclude-folders node_modules dist '*_cache'
      Prune directories by name or glob.

  %(prog)s -e py --dry-run
      Preview what would be included, without writing anything.
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile repository files into a single markdown document.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # -- Input/output --
    io_group = parser.add_argument_group("input / output")
    io_group.add_argument(
        "-f", "--folders",
        nargs="+", type=_dir_path, default=[],
        metavar="DIR",
        help=(
            "Folders to scan recursively. Defaults to '.' when neither "
            "-f nor --files is given."
        ),
    )
    io_group.add_argument(
        "--files",
        nargs="+", type=Path, default=[],
        metavar="FILE",
        help=(
            "Individual files to include unconditionally. These bypass ALL "
            "filtering (patterns, extensions, gitignore, hidden, size limit)."
        ),
    )
    io_group.add_argument(
        "-o", "--output",
        default="codebase.md", metavar="FILE",
        help="Output markdown file (default: %(default)s). Never includes itself.",
    )

    # -- Selection --
    sel_group = parser.add_argument_group(
        "selection",
        description=(
            "What to include. With no selection flags, every text file that "
            "survives the exclusion rules is included. See the epilog below "
            "for the full filtering pipeline and pattern syntax."
        ),
    )
    sel_group.add_argument(
        "--include",
        nargs="+", default=[], metavar="PATTERN",
        help=(
            "Gitignore-style patterns of files to include. Matching files "
            "bypass hidden/gitignore/extension filtering. Without -e this "
            "acts as a whitelist (ONLY matching files are taken); with -e "
            "the result is the union of both. "
            "Examples: 'Makefile', '*.test.js', 'src/**/*.proto', '.github/**'."
        ),
    )
    sel_group.add_argument(
        "-e", "--extensions",
        nargs="+", default=[], metavar="EXT",
        help=(
            "Only include files with these extensions (e.g. py js ts). "
            "Leading dots are optional. Activates extension filtering; "
            "extensionless files then require --include-extensionless or "
            "an --include pattern."
        ),
    )
    sel_group.add_argument(
        "--include-extensionless",
        action="store_true",
        help=(
            "When -e is given, also include files without any extension "
            "(e.g. Makefile, LICENSE). No effect otherwise."
        ),
    )
    sel_group.add_argument(
        "--include-hidden", action="store_true",
        help=(
            "Include hidden files and directories (names starting with '.'). "
            "Alternatively, a path-qualified --include pattern such as "
            "'.github/**' includes just that hidden subtree."
        ),
    )

    # -- Exclusion --
    exc_group = parser.add_argument_group(
        "exclusion",
        description="Exclusions always win, including over --include and --files patterns.",
    )
    exc_group.add_argument(
        "--exclude",
        nargs="+", default=[], metavar="PATTERN",
        help=(
            "Gitignore-style patterns of files/directories to exclude. "
            "Examples: '*.log', 'docs/', '**/generated/**', '/vendor'."
        ),
    )
    exc_group.add_argument(
        "--exclude-folders",
        nargs="+", default=[], metavar="PATTERN",
        help=(
            "Directories to prune entirely, by name, glob or path "
            "(e.g. node_modules '*_cache' build/output). Pruned directories "
            "are never descended into, even for --include patterns."
        ),
    )
    exc_group.add_argument(
        "--exclude-extensions",
        nargs="+", default=[], metavar="EXT",
        help="Exclude files with these extensions, regardless of other settings.",
    )

    # -- Behaviour --
    beh_group = parser.add_argument_group("behaviour")
    beh_group.add_argument(
        "--no-gitignore", action="store_true",
        help="Do not respect .gitignore files found in the scanned folders.",
    )
    beh_group.add_argument(
        "--max-file-size",
        type=int, default=0, metavar="KB",
        help=(
            "Skip files larger than this many KB. 0 = no limit (default). "
            "Does not apply to --files."
        ),
    )
    beh_group.add_argument(
        "--dry-run", action="store_true",
        help="List the files that would be included (with sizes and a tree), "
             "without writing the output.",
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

    # ---- Compile pattern specs (gitignore-style, via pathspec) ----
    include_spec = _compile_spec(args.include, "--include", parser)
    exclude_spec = _compile_spec(args.exclude, "--exclude", parser)
    exclude_dirs_spec = _compile_spec(args.exclude_folders, "--exclude-folders", parser)

    # ---- Extension filtering ----
    extensions: set[str] = {e.lower().lstrip(".") for e in args.extensions}
    exclude_extensions: set[str] = {
        e.lower().lstrip(".") for e in args.exclude_extensions
    }
    extension_filter_active = bool(extensions)

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
        "include_spec": include_spec,
        "include_patterns": args.include,
        "exclude_spec": exclude_spec,
        "exclude_dirs_spec": exclude_dirs_spec,
        "gitignore_spec": gitignore_spec,
        "extension_filter_active": extension_filter_active,
        "extensions": extensions,
        "exclude_extensions": exclude_extensions,
        "include_extensionless": args.include_extensionless,
        "max_file_size": max_file_size,
    }

    # ---- Summary ----
    console.print("[bold blue]repo2md[/]")
    if base_folders:
        console.print(f"  Scanning: {', '.join(str(b) for b in base_folders)}")
    if direct_file_paths:
        console.print(
            f"  Direct files: {', '.join(str(f) for f in direct_file_paths)}"
        )
    console.print(f"  Output: [green]{output_path}[/]")

    if include_spec and extension_filter_active:
        mode = "union of --include patterns and -e extensions"
    elif include_spec:
        mode = "--include whitelist"
    elif extension_filter_active:
        mode = "extension filter"
    else:
        mode = "all files (no selection filter)"
    console.print(f"  Selection: [cyan]{mode}[/]")

    if extension_filter_active:
        console.print(
            f"  Extensions: [green]{', '.join(sorted(extensions))}[/]"
            + (" [cyan]+extensionless[/]" if args.include_extensionless else "")
        )
    if args.include:
        console.print(f"  Include patterns: [green]{', '.join(args.include)}[/]")
    if args.exclude:
        console.print(f"  Exclude patterns: [yellow]{', '.join(args.exclude)}[/]")
    if args.exclude_folders:
        console.print(
            f"  Excluding folders: [yellow]{', '.join(args.exclude_folders)}[/]"
        )
    if exclude_extensions:
        console.print(
            f"  Excluding ext: [yellow]{', '.join(sorted(exclude_extensions))}[/]"
        )
    if args.no_gitignore:
        gitignore_status = "disabled"
    elif gitignore_spec:
        gitignore_status = "respected"
    else:
        gitignore_status = "respected (no patterns found)"
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

    if len(base_folders) == 1:
        root_label = base_folders[0].resolve().name
    elif base_folders:
        root_label = "<multi>"
    else:
        root_label = "."

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
        console.print(format_tree(list(display_paths.values()), root_label))
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
            f.write("## Structure\n\n~~~\n")
            f.write(format_tree(list(display_paths.values()), root_label))
            f.write("\n~~~\n\n---\n\n")
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