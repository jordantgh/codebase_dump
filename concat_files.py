# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pathspec",  # For .gitignore processing
#     "rich",      # For better CLI output
# ]
# ///

import os
import argparse
from pathlib import Path
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import pathspec
from collections import defaultdict
import fnmatch
from rich.console import Console
from rich.progress import track
from rich.logging import RichHandler

# Configure logging with rich
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)

console = Console()

PROJECT_PRESETS = {
    "python": {
        "extensions": [
            "py",
            "pyi",  # Python source and interface files
            "toml",
            "ini",
            "cfg",
            "yml",
            "yaml",  # Config files
            "txt",  # Text files including requirements.txt
            "md",
            "rst",  # Documentation
            "dockerfile",  # Container definitions
        ],
        "exclude_folders": [
            "venv",
            ".venv",
            "env",
            ".env",
            "__pycache__",
            ".pytest_cache",
            "build",
            "dist",
            "*.egg-info",
            ".tox",
            ".mypy_cache",
            ".coverage",
            "htmlcov",
        ],
    },
    "js": {
        "extensions": [
            "js",
            "jsx",
            "ts",
            "tsx",
            "vue",
            "svelte",
            "json",
            "jsonc",
            "html",
            "css",
            "scss",
            "sass",
            "less",
            "mjs",
            "cjs",
            "md",
            "mdx",
            "lock",  # package-lock.json, yarn.lock
        ],
        "exclude_folders": [
            "node_modules",
            "dist",
            "build",
            "coverage",
            ".next",
            ".nuxt",
            ".cache",
            ".parcel-cache",
        ],
    },
    "lowlevel": {
        "extensions": [
            "c",
            "h",
            "cpp",
            "hpp",
            "cc",
            "cxx",
            "asm",
            "s",
            "rs",
            "go",
            "zig",
            "mk",
            "makefile",
            "cmake",
            "txt",
            "md",
        ],
        "exclude_folders": [
            "build",
            "bin",
            "obj",
            "target",
            "debug",
            "release",
            "deps",
        ],
    },
    "ml": {
        "extensions": [
            "py",  # Python source files
            "yaml",
            "yml",
            "json",  # Config files
            "txt",  # Text files including requirements.txt
            "md",
            "rst",  # Documentation
            "dockerfile",
            "cfg",  # Container and config files
        ],
        "exclude_folders": [
            "venv",
            ".venv",
            "__pycache__",
            "data",
            "datasets",
            "checkpoints",
            "runs",
            "logs",
            "tensorboard",
            "wandb",
            "mlruns",
            "models",
        ],
    },
    "datascience": {
        "extensions": [
            "py",  # Python source files
            "r",
            "rmd",  # R files
            "sql",  # SQL queries
            "yaml",
            "yml",  # Config files
            "txt",
            "md",  # Documentation
            "dockerfile",  # Container definitions
        ],
        "exclude_folders": [
            "venv",
            ".venv",
            "__pycache__",
            "data",
            "raw_data",
            "processed_data",
            "interim",
            "external",
            "figures",
            "results",
            "outputs",
        ],
    },
    "web": {
        "extensions": [
            "html",
            "htm",
            "css",
            "scss",
            "sass",
            "less",
            "js",
            "ts",
            "jsx",
            "tsx",
            "php",
            "rb",
            "erb",
            "json",
            "md",
            "svg",
            "xml",
            "webmanifest",
        ],
        "exclude_folders": [
            "node_modules",
            "vendor",
            "dist",
            "build",
            "public/assets",
            "tmp",
            "cache",
            ".sass-cache",
        ],
    },
    "devops": {
        "extensions": [
            "yml",
            "yaml",
            "tf",
            "hcl",
            "dockerfile",
            "conf",
            "sh",
            "bash",
            "json",
            "toml",
            "ini",
            "env",
            "md",
            "txt",
        ],
        "exclude_folders": [
            ".terraform",
            "terraform.tfstate.d",
            "charts",
            "manifests",
            "secrets",
            "keys",
            "certs",
            "logs",
        ],
    },
    "mobile": {
        "extensions": [
            "kt",
            "java",
            "xml",
            "gradle",
            "swift",
            "m",
            "h",
            "plist",
            "dart",
            "yaml",
            "json",
            "md",
        ],
        "exclude_folders": [
            "build",
            ".gradle",
            ".idea",
            "Pods",
            "DerivedData",
            ".dart_tool",
            "build",
            "ios/Pods",
        ],
    },
    "fullstack_js_python": {
        "extensions": [
            # Frontend
            "js",
            "jsx",
            "ts",
            "tsx",
            "vue",
            "css",
            "scss",
            "sass",
            "html",
            "json",
            "svg",
            # Backend
            "py",
            "pyi",
            # Shared
            "yml",
            "yaml",
            "toml",
            "ini",
            "md",
            "rst",
            "txt",
            "dockerfile",
            "env",
            "gitignore",
        ],
        "exclude_folders": [
            # Frontend
            "node_modules",
            "build",
            "dist",
            ".next",
            ".nuxt",
            ".cache",
            # Backend
            "venv",
            ".venv",
            "__pycache__",
            "*.egg-info",
            ".pytest_cache",
            # Shared
            ".git",
            ".idea",
            ".vscode",
        ],
    },
    "fullstack_mobile": {
        "extensions": [
            # Mobile
            "kt",
            "java",
            "swift",
            "dart",
            # Backend
            "py",
            "go",
            "rs",
            # Shared
            "yml",
            "json",
            "md",
            "dockerfile",
        ],
        "exclude_folders": [
            # Mobile
            "Pods",
            "build",
            ".gradle",
            # Backend
            "venv",
            "__pycache__",
            # Shared
            ".git",
            "node_modules",
        ],
    },
}


def normalize_path(path, base_folder):
    """Normalize and resolve paths relative to base folder."""
    try:
        return Path(path).resolve().relative_to(Path(base_folder).resolve())
    except ValueError:
        return None


def load_gitignore(folders):
    """Load .gitignore patterns from multiple folders."""
    gitignore_patterns = []
    for folder in folders:
        gitignore_path = Path(folder) / ".gitignore"
        if gitignore_path.exists():
            with open(gitignore_path, "r") as gitignore_file:
                gitignore_patterns.extend(gitignore_file.readlines())
    return pathspec.PathSpec.from_lines(
        pathspec.patterns.GitWildMatchPattern, gitignore_patterns
    )


def should_process_file(filepath, options):
    """
    Centralized file processing decision logic.

    Args:
        filepath: Path object for the file
        options: dict containing processing options
    """
    path = filepath.resolve()
    relative_path = normalize_path(path, options["base_folder"])
    
    if relative_path is None:
        return False

    # Check if file matches output file
    if path == options["output_file"]:
        return False

    # Hidden file/folder check
    if not options["include_hidden"] and (
        any(p.name.startswith(".") for p in path.parents)
        or path.name.startswith(".")
    ):
        return False

    # Check explicit inclusion by filename
    explicit_include = False
    if options.get("include_files"):
        # Check if filename is in the list or matches any pattern
        if path.name in options["include_files"]:
            explicit_include = True
        # Also check if any pattern matches
        elif any(fnmatch.fnmatch(path.name, pattern) for pattern in options["include_files"]):
            explicit_include = True

    # Check pattern-based inclusion
    if not explicit_include and options.get("include_patterns"):
        # Convert Path to string for pattern matching
        str_path = str(relative_path)
        if any(fnmatch.fnmatch(str_path, pattern) for pattern in options["include_patterns"]):
            explicit_include = True

    # File extension checks
    extension = path.suffix[1:].lower()
    
    # Check if extension should be excluded
    if options.get("exclude_extensions") and extension in options["exclude_extensions"]:
        return False
    
    # Check if extension is included (unless file was explicitly included)
    if not explicit_include and extension not in options["extensions"]:
        return False

    # Check for specific file exclusions
    if any(
        path.samefile(exc) if exc.exists() else path.name == exc.name
        for exc in options["exclude_files"]
    ):
        return False
    
    # Check for pattern-based exclusion
    if options.get("exclude_patterns"):
        str_path = str(relative_path)
        if any(fnmatch.fnmatch(str_path, pattern) for pattern in options["exclude_patterns"]):
            return False

    # Check gitignore patterns
    if options["spec"] and options["spec"].match_file(str(relative_path)):
        return False

    return True


def build_tree(base_folder, exclude_folders, spec, include_hidden):
    """Build a tree structure of the files to be processed."""
    tree = defaultdict(list)
    base_folder = Path(base_folder).resolve()

    for root, dirs, files in os.walk(base_folder):
        current_path = Path(root)

        # Check if current path should be excluded
        should_exclude = any(
            current_path == Path(exc).resolve()
            or Path(exc).resolve() in current_path.parents
            for exc in exclude_folders
        )

        if should_exclude:
            dirs.clear()  # Stop recursion into excluded directories
            continue

        if not include_hidden and current_path.name.startswith("."):
            dirs.clear()
            continue

        relative_path = normalize_path(current_path, base_folder)
        if relative_path is None:
            continue

        # Filter files
        valid_files = [
            f for f in files if (include_hidden or not f.startswith("."))
        ]

        if valid_files:
            tree[current_path].extend(valid_files)

        # Filter dirs in place
        dirs[:] = [d for d in dirs if (include_hidden or not d.startswith("."))]

    return tree


def write_tree_structure(tree, output_file):
    """Write the folder structure to the output file."""
    with open(output_file, "a", encoding="utf-8") as out_f:
        out_f.write("\n## Folder Structure\n\n")
        out_f.write("```\n")

        # Sort folders for consistent output
        sorted_folders = sorted(tree.keys())
        
        # Find the folder with the minimum number of parts (shortest path)
        min_folder = min(sorted_folders, key=lambda p: len(p.parts))

        for i, folder in enumerate(sorted_folders):
            # Calculate relative depth from first common parent
            relative_parts = normalize_path(folder, min_folder)
            depth = len(relative_parts.parts) if relative_parts else 0

            is_last = i == len(sorted_folders) - 1
            prefix = (
                "    " * (depth - 1) + ("└── " if is_last else "├── ")
                if depth > 0
                else ""
            )
            out_f.write(f"{prefix}{folder.name}/\n")

            # Process files in the current folder
            files = sorted(tree[folder])
            for j, file in enumerate(files):
                is_last_file = j == len(files) - 1
                file_prefix = "    " * depth + (
                    "└── " if is_last_file else "├── "
                )
                out_f.write(f"{file_prefix}{file}\n")

        out_f.write("```\n\n")


def process_file(filepath, base_folder, output_file, extensions):
    """Process a single file and append its content to the output file."""
    try:
        filepath = Path(filepath)
        file_extension = filepath.suffix[1:].lower()

        # We can skip the extension check here as it was done in should_process_file
        relative_path = normalize_path(filepath, base_folder)
        if not relative_path:
            return False

        with open(filepath, "r", encoding="utf-8") as in_f:
            content = in_f.read()

        with open(output_file, "a", encoding="utf-8") as out_f:
            out_f.write(f"\n## {relative_path}\n\n")
            out_f.write(f"```{file_extension}\n")
            out_f.write(content)
            out_f.write("\n```\n\n")
            return True

    except UnicodeDecodeError:
        logging.warning(f"Skipping binary file: {filepath}")
        with open(output_file, "a", encoding="utf-8") as out_f:
            out_f.write(f"\n## {filepath.relative_to(base_folder)}\n\n")
            out_f.write("[Binary file content not displayed]\n\n")
    except Exception as e:
        logging.error(f"Error processing file {filepath}: {e}")
    return False


def process_codebase(folders, output_file, **options):
    """Process the entire codebase, handling multiple base folders."""
    processed_files = set()
    trees = {}

    # Process each base folder independently
    for folder in folders:
        base = Path(folder).resolve()
        if not base.exists():
            logging.warning(f"Folder not found: {folder}")
            continue

        folder_tree = build_tree(
            base,
            options["exclude_folders"],
            options["spec"],
            options["include_hidden"],
        )

        # Merge trees while avoiding duplicates
        for path, files in folder_tree.items():
            if path not in trees:
                trees[path] = []
            new_files = [f for f in files if (path / f) not in processed_files]
            trees[path].extend(new_files)
            processed_files.update(path / f for f in new_files)

    # Write structure first
    write_tree_structure(trees, output_file)

    # Process files with consistent options
    processing_options = {
        "base_folder": folders[
            0
        ],  # Use first folder as base for relative paths
        "output_file": Path(output_file).resolve(),
        "extensions": options["extensions"],
        "exclude_extensions": options.get("exclude_extensions", []),
        "exclude_files": options["exclude_files"],
        "include_hidden": options["include_hidden"],
        "include_files": options.get("include_files", []),
        "include_patterns": options.get("include_patterns", []),
        "exclude_patterns": options.get("exclude_patterns", []),
        "spec": options["spec"],
    }

    files_to_process = [
        (path / f, processing_options)
        for path, files in trees.items()
        for f in files
        if should_process_file(path / f, processing_options)
    ]

    return files_to_process


def merge_multiple_presets(ptypes, user_options):
    """Merge multiple preset configurations with user options."""
    if not ptypes:
        return user_options

    # Start with first preset
    merged = PROJECT_PRESETS[ptypes[0]].copy()

    # Merge additional presets
    for ptype in ptypes[1:]:
        preset = PROJECT_PRESETS[ptype]
        merged["extensions"].extend(
            ext
            for ext in preset["extensions"]
            if ext not in merged["extensions"]
        )
        merged["exclude_folders"].extend(
            folder
            for folder in preset["exclude_folders"]
            if folder not in merged["exclude_folders"]
        )

    # Finally merge user options
    if user_options.get("extensions"):
        merged["extensions"].extend(
            ext
            for ext in user_options["extensions"]
            if ext not in merged["extensions"]
        )

    if user_options.get("exclude_folders"):
        merged["exclude_folders"].extend(
            folder
            for folder in user_options["exclude_folders"]
            if folder not in merged["exclude_folders"]
        )

    return merged


def path_type(path_str):
    """Convert string to Path and verify it exists and is a directory."""
    path = Path(path_str)
    if not path.exists():
        raise argparse.ArgumentTypeError(f"Path {path_str} does not exist")
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"Path {path_str} is not a directory")
    return path


def main():
    """Compile codebase into a single markdown file."""
    
    # Create a detailed help description
    description = """
    Compile codebase into a single markdown file.

    This tool scans specified folders and combines all matching files into a single markdown document,
    preserving the folder structure and providing syntax highlighting based on file extensions.
    """
    
    epilog = """
    Project Type Presets Available:
    - python: Python projects
    - js: JavaScript/TypeScript projects
    - fullstack_js_python: React/Vue + Flask/Django projects
    - fullstack_mobile: Mobile + Backend projects
    - lowlevel: Low-level programming projects
    - ml: Machine Learning projects
    - datascience: Data Science projects
    - web: Web development projects
    - devops: DevOps and Infrastructure projects
    - mobile: Mobile app development projects

    Multiple project types can be combined:
    $ python script.py --ptype python js
    """

    parser = argparse.ArgumentParser(
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Add arguments
    parser.add_argument(
        "--ptype",
        choices=list(PROJECT_PRESETS.keys()),
        nargs="+",
        help="Project type preset configuration(s)",
    )
    
    parser.add_argument(
        "-o", "--output",
        default="codebase.md",
        help="Output markdown file (default: codebase.md)",
    )
    
    # File extension filtering
    extension_group = parser.add_argument_group("File Extension Filtering")
    extension_group.add_argument(
        "-e", "--extensions",
        nargs="+",
        default=[],
        help="File extensions to include (default: py toml md rst js css html yml yaml json)",
    )
    extension_group.add_argument(
        "--exclude-extensions",
        nargs="+",
        default=[],
        help="File extensions to exclude (overrides --extensions)",
    )
    
    # Folder filtering
    folder_group = parser.add_argument_group("Folder Filtering")
    folder_group.add_argument(
        "-f", "--folders",
        nargs="+",
        type=path_type,
        default=[Path(".")],
        help="Folders to search (default: current directory)",
    )
    folder_group.add_argument(
        "--exclude-folders",
        nargs="+",
        default=["venv", ".venv", "__pycache__", "node_modules", "tests", ".git", ".idea", ".vscode"],
        help="Folders to exclude (default: venv .venv __pycache__ node_modules tests .git .idea .vscode)",
    )
    
    # File filtering
    file_group = parser.add_argument_group("File Filtering")
    file_group.add_argument(
        "--exclude-files",
        nargs="+",
        default=[],
        help="Files to exclude",
    )
    file_group.add_argument(
        "--include-files",
        nargs="+",
        default=[],
        help="Specific files to include (overrides extension filtering)",
    )
    
    # Pattern filtering
    pattern_group = parser.add_argument_group("Pattern Filtering")
    pattern_group.add_argument(
        "--include-patterns",
        nargs="+",
        default=[],
        help="Glob patterns to include (e.g. '*.config.js' '**/*.test.py')",
    )
    pattern_group.add_argument(
        "--exclude-patterns",
        nargs="+", 
        default=[],
        help="Glob patterns to exclude",
    )
    
    # Other options
    other_group = parser.add_argument_group("Other Options")
    other_group.add_argument(
        "--no-gitignore",
        action="store_true",
        help="Disable .gitignore respect (default: False)",
    )
    other_group.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden files and folders (default: False)",
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Process the arguments
    ptype = args.ptype
    output = args.output
    extensions = args.extensions
    exclude_extensions = args.exclude_extensions
    folders = args.folders
    exclude_files = args.exclude_files
    exclude_folders = args.exclude_folders
    include_files = args.include_files
    include_patterns = args.include_patterns
    exclude_patterns = args.exclude_patterns
    no_gitignore = args.no_gitignore
    include_hidden = args.include_hidden
    
    # Convert extensions to list and normalize
    extensions = [ext.lower().lstrip(".") for ext in extensions]
    exclude_extensions = [ext.lower().lstrip(".") for ext in exclude_extensions]

    # If project type is specified, merge with preset configurations
    if ptype:
        merged_options = merge_multiple_presets(
            ptype,
            {
                "extensions": extensions, 
                "exclude_folders": exclude_folders,
                "exclude_extensions": exclude_extensions
            },
        )
        extensions = merged_options["extensions"]
        exclude_folders = merged_options["exclude_folders"]
        
        # We don't want to override explicit exclude_extensions if provided by user
        if not args.exclude_extensions and "exclude_extensions" in merged_options:
            exclude_extensions = merged_options["exclude_extensions"]

        console.print(
            f"[bold blue]Using project presets: {', '.join(ptype)}[/]"
        )

    # Normalize file paths
    exclude_files = [Path(file).resolve() for file in exclude_files]
    respect_gitignore = not no_gitignore

    console.print("[bold blue]Starting codebase compilation[/]")
    console.print(f"Output file: [green]{output}[/]")
    console.print(f"Scanning folders: [green]{', '.join(str(f) for f in folders)}[/]")
    
    if include_files:
        console.print(f"Including specific files: [green]{', '.join(include_files)}[/]")
    if include_patterns:
        console.print(f"Including patterns: [green]{', '.join(include_patterns)}[/]")
    if exclude_patterns:
        console.print(f"Excluding patterns: [yellow]{', '.join(exclude_patterns)}[/]")
    if exclude_extensions:
        console.print(f"Excluding extensions: [yellow]{', '.join(exclude_extensions)}[/]")

    spec = load_gitignore(folders) if respect_gitignore else None

    # Initialize output file
    with open(output, "w", encoding="utf-8") as f:
        f.write("# Compiled Codebase\n\n")

    # Process codebase and get files to process
    files_to_process = process_codebase(
        folders,
        output,
        exclude_folders=exclude_folders,
        exclude_files=exclude_files,
        extensions=extensions,
        exclude_extensions=exclude_extensions,
        include_files=include_files,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        include_hidden=include_hidden,
        spec=spec,
    )

    # Process files in parallel
    processed_count = 0
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = []
        for filepath, options in track(
            files_to_process, description="Processing files"
        ):
            futures.append(
                executor.submit(
                    process_file,
                    filepath,
                    options["base_folder"],
                    output,
                    options["extensions"],
                )
            )

        for future in as_completed(futures):
            try:
                if future.result():
                    processed_count += 1
            except Exception as e:
                logging.error(f"Unexpected error: {e}")

    console.print(
        f"[bold green]✓[/] Processed {processed_count} files into [blue]{output}[/]"
    )


if __name__ == "__main__":
    main()
