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
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.logging import RichHandler
from typing import Optional, Tuple, Dict, List, Any

# Configure logging with rich
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
log = logging.getLogger("rich")
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
            "gitignore",  # Git ignore files
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
            ".git",
            ".idea",
            ".vscode",
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
            "gitignore",
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
            ".git",
            ".idea",
            ".vscode",
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
            "gitignore",
        ],
        "exclude_folders": [
            "build",
            "bin",
            "obj",
            "target",
            "debug",
            "release",
            "deps",
            ".git",
            ".idea",
            ".vscode",
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
            "gitignore",
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
            ".git",
            ".idea",
            ".vscode",
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
            "gitignore",
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
            ".git",
            ".idea",
            ".vscode",
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
            "gitignore",
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
            ".git",
            ".idea",
            ".vscode",
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
            "gitignore",
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
            ".git",
            ".idea",
            ".vscode",
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
            "gitignore",
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
            ".git",
            ".vscode",
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
            "svelte",
            "css",
            "scss",
            "sass",
            "less",
            "html",
            "json",
            "jsonc",
            "svg",
            "mjs",
            "cjs",
            "mdx",
            "lock",
            # Backend
            "py",
            "pyi",
            "toml",
            "ini",
            "cfg",
            "rst",
            # Shared
            "yml",
            "yaml",
            "md",
            "txt",
            "dockerfile",
            "env",
            "gitignore",
            "webmanifest",
        ],
        "exclude_folders": [
            # Frontend
            "node_modules",
            "build",
            "dist",
            ".next",
            ".nuxt",
            ".cache",
            ".parcel-cache",
            "coverage",
            # Backend
            "venv",
            ".venv",
            "__pycache__",
            "*.egg-info",
            ".pytest_cache",
            ".tox",
            ".mypy_cache",
            ".coverage",
            "htmlcov",
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
            "xml",
            "gradle",
            "swift",
            "m",
            "h",
            "plist",
            "dart",
            # Backend
            "py",
            "go",
            "rs",
            "js",
            "ts",
            "php",
            "rb",
            # Shared
            "yml",
            "yaml",
            "json",
            "md",
            "txt",
            "dockerfile",
            "gitignore",
        ],
        "exclude_folders": [
            # Mobile
            "build",
            ".gradle",
            ".idea",
            "Pods",
            "DerivedData",
            ".dart_tool",
            "ios/Pods",
            # Backend
            "venv",
            ".venv",
            "__pycache__",
            "target",
            "node_modules",
            "vendor",
            # Shared
            ".git",
            ".vscode",
        ],
    },
}


def normalize_path(path: Path, base_folder: Path) -> Optional[Path]:
    """Normalize and resolve paths relative to base folder."""
    try:
        resolved_path = path.resolve()
        resolved_base = base_folder.resolve()
        # Check if the path is within the base folder
        if (
            resolved_base not in resolved_path.parents
            and resolved_path != resolved_base
        ):
            # Allow files directly in the base folder
            if resolved_path.parent == resolved_base:
                return Path(resolved_path.name)
            # log.debug(f"Path {resolved_path} not relative to base {resolved_base}")
            return None
        return resolved_path.relative_to(resolved_base)
    except ValueError:
        # log.debug(f"ValueError normalizing {path} against {base_folder}")
        return None
    except Exception as e:
        log.warning(f"Error normalizing path {path}: {e}")
        return None


def load_gitignore(folders: List[Path]) -> Optional[pathspec.PathSpec]:
    """Load .gitignore patterns from multiple folders."""
    gitignore_patterns = []
    for folder in folders:
        gitignore_path = folder.resolve() / ".gitignore"
        if gitignore_path.is_file():
            try:
                with open(
                    gitignore_path, "r", encoding="utf-8"
                ) as gitignore_file:
                    gitignore_patterns.extend(gitignore_file.readlines())
            except Exception as e:
                log.warning(f"Could not read .gitignore {gitignore_path}: {e}")
        else:
            log.debug(f".gitignore not found in {folder}")

    if not gitignore_patterns:
        log.debug("No .gitignore patterns found.")
        return None
    try:
        return pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern, gitignore_patterns
        )
    except Exception as e:
        log.error(f"Error parsing .gitignore patterns: {e}")
        return None


def should_process_file(filepath: Path, options: Dict[str, Any]) -> bool:
    """
    Centralized file processing decision logic.

    Args:
        filepath: Path object for the file
        options: dict containing processing options including 'base_folders' list
    """
    try:
        path = filepath.resolve()

        # Find the correct base folder for relative path calculation
        base_folder = None
        relative_path_str = None
        for bf in options["base_folders"]:
            resolved_bf = bf.resolve()
            if resolved_bf == path or resolved_bf in path.parents:
                base_folder = resolved_bf
                try:
                    relative_path_str = str(path.relative_to(base_folder))
                    break
                except ValueError:
                    # This can happen if path IS the base folder, handle directly
                    if path == resolved_bf:
                        # We generally don't process the base folder itself as a file
                        return False
                    continue  # Try next base folder

        if base_folder is None or relative_path_str is None:
            log.debug(
                f"Skipping {path}: Could not determine relative path from bases {options['base_folders']}"
            )
            return False

        # Prevent processing the output file itself
        if (
            options.get("output_file_resolved")
            and path == options["output_file_resolved"]
        ):
            log.debug(f"Skipping output file: {path}")
            return False

        # Hidden file/folder check - check relative path components
        if not options.get("include_hidden", False):
            # Check components of the relative path and the filename itself
            path_components = [path.name] + [
                p.name for p in Path(relative_path_str).parents
            ]
            if any(
                part.startswith(".") for part in path_components if part != "."
            ):
                log.debug(f"Skipping hidden file/path: {relative_path_str}")
                return False

        # --- Explicit Inclusion Checks ---
        explicitly_included = False
        # 1. Direct filename match in include_files
        if (
            options.get("include_files")
            and path.name in options["include_files"]
        ):
            log.debug(f"Explicitly including by filename: {path.name}")
            explicitly_included = True
        # 2. Glob pattern match in include_files against filename
        elif options.get("include_files") and any(
            fnmatch.fnmatch(path.name, pattern)
            for pattern in options["include_files"]
        ):
            log.debug(f"Explicitly including by filename pattern: {path.name}")
            explicitly_included = True
        # 3. Glob pattern match in include_patterns against relative path
        elif options.get("include_patterns") and any(
            fnmatch.fnmatch(relative_path_str, pattern)
            for pattern in options["include_patterns"]
        ):
            log.debug(
                f"Explicitly including by path pattern: {relative_path_str}"
            )
            explicitly_included = True

        # --- Exclusion Checks ---
        # 1. Specific file exclusions by resolved path or name
        if options.get("exclude_files"):
            resolved_exclude_files = options[
                "exclude_files"
            ]  # Assume already resolved
            if any(path == exc_path for exc_path in resolved_exclude_files):
                log.debug(
                    f"Excluding specific file by path: {relative_path_str}"
                )
                return False
            if any(
                path.name == exc_path.name
                for exc_path in resolved_exclude_files
            ):
                log.debug(f"Excluding specific file by name: {path.name}")
                return False

        # 2. Pattern-based exclusion against relative path
        if options.get("exclude_patterns") and any(
            fnmatch.fnmatch(relative_path_str, pattern)
            for pattern in options["exclude_patterns"]
        ):
            log.debug(f"Excluding by pattern: {relative_path_str}")
            return False

        # 3. Gitignore check against relative path
        if options.get("spec") and options["spec"].match_file(
            relative_path_str
        ):
            log.debug(f"Excluding by .gitignore: {relative_path_str}")
            return False

        # 4. Folder exclusion check (already partially handled by os.walk, but good failsafe)
        # Ensure exclude_folders are resolved for comparison
        resolved_exclude_folders = options.get("resolved_exclude_folders", [])
        if any(
            resolved_exc_folder == path.parent
            or resolved_exc_folder in path.parents
            for resolved_exc_folder in resolved_exclude_folders
        ):
            log.debug(
                f"Excluding because parent folder is excluded: {relative_path_str}"
            )
            return False
        # Also check for glob patterns in exclude_folders
        if any(
            fnmatch.fnmatch(part, pattern)
            for part in Path(relative_path_str).parts
            for pattern in options.get("exclude_folder_patterns", [])
        ):
            log.debug(
                f"Excluding because parent folder matches pattern: {relative_path_str}"
            )
            return False

        # --- Extension Checks (only if not explicitly included) ---
        if not explicitly_included:
            extension = path.suffix[1:].lower() if path.suffix else ""
            # Check excluded extensions first
            if (
                options.get("exclude_extensions")
                and extension in options["exclude_extensions"]
            ):
                log.debug(f"Excluding by extension: {relative_path_str}")
                return False
            # Check included extensions
            if (
                not options.get("extensions")
                or extension not in options["extensions"]
            ):
                log.debug(
                    f"Skipping due to extension (not included or excluded): {relative_path_str}"
                )
                return False

        # If it passed all checks, process it
        log.debug(f"Including file: {relative_path_str}")
        return True

    except Exception as e:
        log.error(
            f"Error in should_process_file for {filepath}: {e}", exc_info=True
        )
        return False


def build_file_list(
    base_folders: List[Path],
    options: Dict[str, Any],
) -> Tuple[List[Path], Dict[Path, Path]]:
    """
    Build a list of files to be processed, respecting exclusions.
    Returns a tuple: (list_of_files_to_process, map_of_file_to_its_base_folder).
    """
    files_to_process = set()
    file_to_base_map = {}

    # Resolve exclude folders once for efficiency
    resolved_exclude_folders = {f.resolve() for f in options["exclude_folders"]}
    options["resolved_exclude_folders"] = (
        resolved_exclude_folders  # Pass resolved paths down
    )

    # Separate glob patterns from direct folder names in exclude_folders
    exclude_folder_patterns = [
        f
        for f in options.get("exclude_folders_raw", [])
        if "*" in f or "?" in f or "[" in f
    ]
    options["exclude_folder_patterns"] = exclude_folder_patterns

    log.info(f"Scanning folders: {[str(bf) for bf in base_folders]}...")
    for base_folder in base_folders:
        resolved_base = base_folder.resolve()
        log.debug(f"Processing base folder: {resolved_base}")

        for root, dirs, files in os.walk(resolved_base, topdown=True):
            current_path = Path(root).resolve()

            # --- Directory Exclusion Logic ---
            # 1. Exact match or parent match with resolved excluded folders
            if any(
                current_path == excluded or excluded in current_path.parents
                for excluded in resolved_exclude_folders
            ):
                log.debug(
                    f"Excluding directory (and subdirectories): {current_path} due to exact/parent match"
                )
                dirs.clear()  # Don't recurse further
                continue

            # 2. Hidden directory check
            if (
                not options.get("include_hidden", False)
                and current_path.name.startswith(".")
                and current_path != resolved_base
            ):
                log.debug(
                    f"Excluding hidden directory (and subdirectories): {current_path}"
                )
                dirs.clear()
                continue

            # 3. Check against exclude_folder_patterns (glob)
            # Create relative path for pattern matching folders
            try:
                relative_dir_path_str = str(
                    current_path.relative_to(resolved_base)
                )
            except ValueError:
                relative_dir_path_str = "."  # Base directory itself

            if any(
                fnmatch.fnmatch(relative_dir_path_str, pattern)
                or fnmatch.fnmatch(current_path.name, pattern)
                for pattern in exclude_folder_patterns
            ):
                log.debug(
                    f"Excluding directory (and subdirectories): {current_path} due to pattern match"
                )
                dirs.clear()
                continue

            # Filter directories in place for recursion
            original_dirs = list(dirs)  # Copy before modifying
            dirs[:] = [
                d
                for d in original_dirs
                if not (
                    # Check resolved path
                    (current_path / d).resolve() in resolved_exclude_folders
                    or
                    # Check hidden
                    (
                        not options.get("include_hidden", False)
                        and d.startswith(".")
                    )
                    or
                    # Check patterns against dir name or relative path part
                    any(
                        fnmatch.fnmatch(d, pattern)
                        or fnmatch.fnmatch(
                            str(Path(relative_dir_path_str) / d), pattern
                        )
                        for pattern in exclude_folder_patterns
                    )
                )
            ]
            log.debug(
                f"Kept subdirs in {current_path.name}: {dirs} (from {original_dirs})"
            )

            # --- File Processing ---
            for filename in files:
                filepath = current_path / filename

                # Use the should_process_file function for consistent checks
                # Pass the list of base_folders for relative path checking
                if should_process_file(filepath, options):
                    resolved_filepath = filepath.resolve()
                    if resolved_filepath not in files_to_process:
                        files_to_process.add(resolved_filepath)
                        file_to_base_map[resolved_filepath] = (
                            resolved_base  # Store which base folder it came from
                        )
                # else: # Already logged in should_process_file
                #    log.debug(f"Skipping file {filepath} based on rules.")

    log.info(f"Found {len(files_to_process)} files matching criteria.")
    return sorted(list(files_to_process)), file_to_base_map


def write_tree_structure(
    files_to_process: List[Path],
    file_to_base_map: Dict[Path, Path],
    output_filepath: Path,
    base_folders: List[Path],
):
    """Write the folder structure derived from the list of files."""
    tree = defaultdict(list)
    processed_relative_paths = set()

    # Determine the common ancestor for display if multiple base folders
    if len(base_folders) > 1:
        try:
            common_ancestor = Path(
                os.path.commonpath([b.resolve() for b in base_folders])
            )
            log.debug(
                f"Using common ancestor for tree display: {common_ancestor}"
            )
        except ValueError:
            common_ancestor = (
                None  # Cannot find common path (e.g., different drives)
            )
            log.warning(
                "Cannot determine common path for base folders, tree structure might look disjointed."
            )
    elif base_folders:
        common_ancestor = (
            base_folders[0].resolve().parent
        )  # Show the base folder itself
    else:
        common_ancestor = Path(".")  # Should not happen if folders is required

    for file_path in files_to_process:
        base_folder = file_to_base_map.get(file_path)
        if not base_folder:
            log.warning(
                f"Could not find base folder for {file_path}, skipping in tree."
            )
            continue

        try:
            # Calculate path relative to the *common ancestor* for tree structure
            if common_ancestor:
                display_rel_path = file_path.relative_to(common_ancestor)
            else:  # Fallback to relative to its own base if no common ancestor
                display_rel_path = file_path.relative_to(base_folder)

            # Add intermediate directories to the tree
            parent = display_rel_path.parent
            while parent != Path("."):
                # Create relative path for the parent folder itself
                current_parent_rel_path = parent
                if current_parent_rel_path not in processed_relative_paths:
                    tree[current_parent_rel_path]  # Just ensure the key exists
                    processed_relative_paths.add(current_parent_rel_path)
                parent = parent.parent

            tree[display_rel_path.parent].append(display_rel_path.name)
            processed_relative_paths.add(display_rel_path)

        except ValueError:
            log.warning(
                f"Could not make {file_path} relative to {common_ancestor or base_folder}, skipping in tree."
            )
        except Exception as e:
            log.error(f"Error processing path for tree {file_path}: {e}")

    # Sort folders and files for consistent output
    sorted_paths = sorted(tree.keys())

    try:
        with open(output_filepath, "a", encoding="utf-8") as out_f:
            out_f.write("## File and Folder Structure\n\n")
            out_f.write("```\n")

            # Store the state of prefix parts for proper tree drawing
            prefix_levels: Dict[int, bool] = {}  # depth -> is_last

            last_toplevel_path = sorted_paths[-1] if sorted_paths else None

            for i, dir_rel_path in enumerate(sorted_paths):
                parts = list(dir_rel_path.parts)
                depth = len(parts)

                # Determine current prefix based on parent levels
                line_prefix = ""
                for d in range(depth):
                    is_parent_last = prefix_levels.get(d, False)
                    if d < depth - 1:  # Connector for intermediate paths
                        line_prefix += "    " if is_parent_last else "│   "
                    else:  # Connector for the current directory name
                        is_last_entry = (i == len(sorted_paths) - 1) or (
                            depth > 0
                            and not str(sorted_paths[i + 1]).startswith(
                                str(dir_rel_path) + os.sep
                            )
                        )

                        line_prefix += "└── " if is_last_entry else "├── "
                        prefix_levels[depth] = (
                            is_last_entry  # Store if this level is last among siblings
                        )

                if parts:
                    out_f.write(f"{line_prefix}{parts[-1]}/\n")
                else:  # Handle root case "." if necessary (though often empty)
                    if common_ancestor:
                        out_f.write(
                            f"{common_ancestor.name}/\n"
                        )  # Or "."? Decide representation
                    else:
                        out_f.write(".\n")

                # Process files in the current directory
                files_in_dir = sorted(tree[dir_rel_path])
                for j, filename in enumerate(files_in_dir):
                    is_last_file = j == len(files_in_dir) - 1

                    file_line_prefix = ""
                    for d in range(depth + 1):
                        is_parent_last = prefix_levels.get(d, False)
                        if (
                            d < depth
                        ):  # Connector for intermediate paths for the file
                            file_line_prefix += (
                                "    " if is_parent_last else "│   "
                            )
                        else:  # Connector for the file itself
                            # If the directory itself was the last entry at its level, files under it use spaces
                            parent_dir_was_last = prefix_levels.get(
                                depth, False
                            )
                            file_line_prefix += (
                                "    " if parent_dir_was_last else "│   "
                            )

                    file_line_prefix += "└── " if is_last_file else "├── "
                    out_f.write(f"{file_line_prefix}{filename}\n")

            out_f.write("```\n\n")
            out_f.write("---\n\n")  # Separator
    except Exception as e:
        log.error(f"Failed to write tree structure to {output_filepath}: {e}")


# MODIFIED: Return content instead of writing
def process_file(
    filepath: Path, base_folder: Path
) -> Optional[Tuple[Path, str]]:
    """
    Reads a single file and returns its relative path and formatted content.
    Returns None if processing fails or file is binary.
    """
    try:
        relative_path = normalize_path(filepath, base_folder)
        if not relative_path:
            log.warning(
                f"Could not get relative path for {filepath} against {base_folder}"
            )
            return None  # Should not happen if called correctly

        file_extension = (
            filepath.suffix[1:].lower() if filepath.suffix else "txt"
        )  # Default to txt if no extension

        log.debug(f"Reading file: {filepath}")
        with open(filepath, "r", encoding="utf-8") as in_f:
            content = in_f.read()

        # Format the output string
        formatted_content = f"## `{relative_path}`\n\n"
        formatted_content += f"```{file_extension}\n"
        formatted_content += (
            content.strip()
        )  # Remove leading/trailing whitespace from content
        formatted_content += "\n```\n\n"

        return (relative_path, formatted_content)

    except UnicodeDecodeError:
        log.warning(f"Skipping binary file: {filepath}")
        # Optionally return a placeholder
        relative_path = normalize_path(filepath, base_folder)
        if relative_path:
            formatted_content = f"## `{relative_path}`\n\n"
            formatted_content += "[Binary file content not displayed]\n\n"
            return (relative_path, formatted_content)
        return None
    except Exception as e:
        log.error(f"Error processing file {filepath}: {e}", exc_info=False)
        return None


def merge_multiple_presets(
    ptypes: List[str], user_options: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge multiple preset configurations with user options."""
    if not ptypes:
        return user_options

    # Start with a deep copy of the first preset
    first_preset = PROJECT_PRESETS.get(ptypes[0])
    if not first_preset:
        log.warning(f"Preset '{ptypes[0]}' not found. Ignoring.")
        merged = {"extensions": [], "exclude_folders": []}
    else:
        # Make copies to avoid modifying the original presets
        merged = {
            "extensions": list(first_preset.get("extensions", [])),
            "exclude_folders": list(first_preset.get("exclude_folders", [])),
        }

    # Merge additional presets
    for ptype in ptypes[1:]:
        preset = PROJECT_PRESETS.get(ptype)
        if not preset:
            log.warning(f"Preset '{ptype}' not found. Ignoring.")
            continue

        # Use sets for efficient merging and deduplication
        merged["extensions"] = list(
            set(merged["extensions"]) | set(preset.get("extensions", []))
        )
        merged["exclude_folders"] = list(
            set(merged["exclude_folders"])
            | set(preset.get("exclude_folders", []))
        )

    # Apply user options - User options generally ADD to presets
    # Extensions: Add user extensions unless they are already present.
    user_extensions = user_options.get("extensions", [])
    if user_extensions:
        merged["extensions"] = list(
            set(merged["extensions"]) | set(user_extensions)
        )

    # Exclude Folders: Add user exclusions unless already present.
    user_exclude_folders = user_options.get("exclude_folders", [])
    if user_exclude_folders:
        merged["exclude_folders"] = list(
            set(merged["exclude_folders"]) | set(user_exclude_folders)
        )

    # Exclude Extensions: User overrides preset (if provided)
    # If user specified --exclude-extensions, use that. Otherwise, use merged preset ones (currently not in presets).
    if (
        "exclude_extensions" in user_options
        and user_options["exclude_extensions"]
    ):
        merged["exclude_extensions"] = list(
            set(user_options["exclude_extensions"])
        )
    else:
        # Let's add capability for presets to exclude extensions too
        preset_exclude_extensions = set()
        for ptype in ptypes:
            preset = PROJECT_PRESETS.get(ptype)
            if preset and "exclude_extensions" in preset:
                preset_exclude_extensions.update(preset["exclude_extensions"])
        if preset_exclude_extensions:
            merged["exclude_extensions"] = list(preset_exclude_extensions)
        # Keep empty list if neither user nor presets defined it
        elif "exclude_extensions" not in merged:
            merged["exclude_extensions"] = []

    log.debug(f"Merged Extensions: {merged.get('extensions')}")
    log.debug(f"Merged Exclude Folders: {merged.get('exclude_folders')}")
    log.debug(f"Merged Exclude Extensions: {merged.get('exclude_extensions')}")

    return merged


def path_type(path_str: str) -> Path:
    """Convert string to Path and verify it exists and is a directory."""
    path = Path(path_str)
    if not path.exists():
        raise argparse.ArgumentTypeError(f"Path '{path_str}' does not exist.")
    if not path.is_dir():
        raise argparse.ArgumentTypeError(
            f"Path '{path_str}' is not a directory."
        )
    return path


def main():
    """Compile codebase into a single markdown file."""
    description = """
    Compile codebase files into a single markdown file.

    Scans specified folders, filters files based on presets, extensions,
    exclusions (.gitignore respected by default), and combines content
    into one Markdown file with structure and code blocks.
    """
    epilog = f"""
    Project Type Presets Available:
    {", ".join(PROJECT_PRESETS.keys())}

    Example: Combine Python backend and JS frontend
    $ python compile_script.py --ptype python js -f ./backend ./frontend -o fullstack_code.md
    """

    parser = argparse.ArgumentParser(
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # --- Input/Output ---
    parser.add_argument(
        "-f",
        "--folders",
        nargs="+",
        type=path_type,
        default=[Path(".")],
        help="Folders to search (default: current directory).",
        metavar="FOLDER",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="codebase.md",
        help="Output markdown file (default: codebase.md).",
        metavar="FILE",
    )

    # --- Presets ---
    parser.add_argument(
        "--ptype",
        choices=list(PROJECT_PRESETS.keys()),
        nargs="+",
        help="Project type preset(s) to use for default filtering.",
        metavar="PRESET",
    )

    # --- Filtering Groups ---
    ext_group = parser.add_argument_group("Extension Filtering")
    ext_group.add_argument(
        "-e",
        "--extensions",
        nargs="+",
        default=[],
        help="Explicitly include these file extensions (e.g., 'py', 'js'). Adds to preset extensions.",
        metavar="EXT",
    )
    ext_group.add_argument(
        "--exclude-extensions",
        nargs="+",
        default=[],
        help="Explicitly exclude these file extensions (overrides includes and presets).",
        metavar="EXT",
    )

    folder_group = parser.add_argument_group("Folder/File Path Filtering")
    folder_group.add_argument(
        "--exclude-folders",
        nargs="+",
        default=[],
        help="Exclude these folder names or relative paths (globs supported, e.g., 'dist', '**/temp*'). Adds to preset exclusions.",
        metavar="FOLDER/PATTERN",
    )
    folder_group.add_argument(
        "--exclude-files",
        nargs="+",
        default=[],
        help="Exclude specific file names or paths.",
        metavar="FILE",
    )
    folder_group.add_argument(
        "--include-files",
        nargs="+",
        default=[],
        help="Explicitly include specific file names or paths (globs supported, e.g. 'config.yaml', '*.test.js'). Bypasses extension checks for matched files.",
        metavar="FILE/PATTERN",
    )
    folder_group.add_argument(
        "--include-patterns",
        nargs="+",
        default=[],
        help="Explicitly include files matching these glob patterns relative to base folders (e.g., 'src/**/*.py'). Bypasses extension checks.",
        metavar="PATTERN",
    )
    folder_group.add_argument(
        "--exclude-patterns",
        nargs="+",
        default=[],
        help="Exclude files matching these glob patterns relative to base folders (e.g., '**/*.log', 'docs/*'). Applied after includes.",
        metavar="PATTERN",
    )

    # --- Behavior Options ---
    behavior_group = parser.add_argument_group("Behavior Options")
    behavior_group.add_argument(
        "--no-gitignore",
        action="store_true",
        help="Do not read or respect .gitignore files.",
    )
    behavior_group.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden files and folders (those starting with '.').",
    )
    behavior_group.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging for detailed execution information.",
    )

    args = parser.parse_args()

    # --- Configure Logging Level ---
    if args.verbose:
        log.setLevel(logging.DEBUG)
        log.debug("Verbose logging enabled.")
    else:
        log.setLevel(logging.INFO)

    # --- Process Arguments and Presets ---
    output_file = Path(args.output)
    output_file_resolved = output_file.resolve()  # Resolve output path early
    base_folders = args.folders
    respect_gitignore = not args.no_gitignore

    # Normalize extensions
    user_extensions = {ext.lower().lstrip(".") for ext in args.extensions}
    user_exclude_extensions = {
        ext.lower().lstrip(".") for ext in args.exclude_extensions
    }

    # Store raw exclude folders for pattern matching later
    user_exclude_folders_raw = args.exclude_folders
    # Resolve non-pattern exclude folders now
    user_exclude_folders_resolved = {
        Path(f).resolve()
        for f in user_exclude_folders_raw
        if "*" not in f and "?" not in f and "[" not in f
    }

    user_exclude_files_resolved = {
        Path(f).resolve() for f in args.exclude_files
    }  # Assume these are specific files

    options = {
        "extensions": list(user_extensions),
        "exclude_folders": user_exclude_folders_raw,  # Keep raw for merging logic
        "exclude_extensions": list(user_exclude_extensions),
    }

    if args.ptype:
        console.print(
            f"[bold blue]Applying project presets: {', '.join(args.ptype)}[/]"
        )
        merged_options = merge_multiple_presets(args.ptype, options)
        # Update options with merged values
        final_extensions = set(merged_options.get("extensions", []))
        final_exclude_folders_raw = set(
            merged_options.get("exclude_folders", [])
        )  # Use set for deduplication
        final_exclude_extensions = set(
            merged_options.get("exclude_extensions", [])
        )
        log.debug(f"Extensions after presets: {final_extensions}")
        log.debug(f"Exclude Folders after presets: {final_exclude_folders_raw}")
        log.debug(
            f"Exclude Extensions after presets: {final_exclude_extensions}"
        )
    else:
        # Use user-provided options directly if no preset
        final_extensions = user_extensions
        final_exclude_folders_raw = set(user_exclude_folders_raw)
        final_exclude_extensions = user_exclude_extensions
        log.debug("No presets specified, using command-line options.")

    # Final filtering options dictionary
    processing_options = {
        "base_folders": base_folders,
        "output_file_resolved": output_file_resolved,
        "extensions": list(final_extensions),
        "exclude_extensions": list(final_exclude_extensions),
        "exclude_folders_raw": list(
            final_exclude_folders_raw
        ),  # Pass raw for build_file_list pattern matching
        # Resolve non-pattern exclude folders once
        "exclude_folders": [
            Path(f)
            for f in final_exclude_folders_raw
            if "*" not in f and "?" not in f and "[" not in f
        ],
        "exclude_files": list(user_exclude_files_resolved),
        "include_files": args.include_files,  # Keep raw for filename/pattern matching
        "include_patterns": args.include_patterns,
        "exclude_patterns": args.exclude_patterns,
        "include_hidden": args.include_hidden,
        "spec": load_gitignore(base_folders) if respect_gitignore else None,
    }

    console.print(f"[bold blue]Starting codebase compilation[/]")
    console.print(f"Output file: [green]{output_file}[/]")
    if final_extensions:
        console.print(
            f"Including extensions: [green]{', '.join(sorted(list(final_extensions)))}[/]"
        )
    if final_exclude_extensions:
        console.print(
            f"Excluding extensions: [yellow]{', '.join(sorted(list(final_exclude_extensions)))}[/]"
        )
    if processing_options["exclude_folders_raw"]:
        console.print(
            f"Excluding folders/patterns: [yellow]{', '.join(sorted(processing_options['exclude_folders_raw']))}[/]"
        )
    if processing_options["exclude_files"]:
        console.print(
            f"Excluding specific files: [yellow]{', '.join(f.name for f in processing_options['exclude_files'])}[/]"
        )
    if processing_options["include_files"]:
        console.print(
            f"Including specific files/patterns: [green]{', '.join(processing_options['include_files'])}[/]"
        )
    if processing_options["include_patterns"]:
        console.print(
            f"Including path patterns: [green]{', '.join(processing_options['include_patterns'])}[/]"
        )
    if processing_options["exclude_patterns"]:
        console.print(
            f"Excluding path patterns: [yellow]{', '.join(processing_options['exclude_patterns'])}[/]"
        )
    if respect_gitignore and processing_options["spec"]:
        console.print(f"Respecting .gitignore: [cyan]Yes[/]")
    elif respect_gitignore:
        console.print(
            f"Respecting .gitignore: [cyan]Yes (but no patterns found/loaded)[/]"
        )
    else:
        console.print(f"Respecting .gitignore: [yellow]No[/]")
    console.print(
        f"Including hidden files/folders: [cyan]{'Yes' if args.include_hidden else 'No'}[/]"
    )

    # --- Build the list of files ---
    # This now handles walking the directories and applying filtering rules
    files_to_process, file_to_base_map = build_file_list(
        base_folders, processing_options
    )

    if not files_to_process:
        log.warning("No files found matching the criteria. Exiting.")
        return

    # --- Write Initial Structure ---
    try:
        output_file.parent.mkdir(
            parents=True, exist_ok=True
        )  # Ensure output directory exists
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"# Codebase Compilation: {output_file.name}\n\n")
            f.write(
                f"Folders Scanned: `{'`, `'.join(str(bf) for bf in base_folders)}`\n\n"
            )
            # Add other meta info if desired
        write_tree_structure(
            files_to_process, file_to_base_map, output_file, base_folders
        )
    except Exception as e:
        log.error(f"Failed to write initial header or tree structure: {e}")
        return

    # --- Process Files Concurrently ---
    processed_content = {}  # Store results: {relative_path: formatted_content}
    skipped_count = 0

    # Use Rich Progress for better feedback
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "Processing files", total=len(files_to_process)
        )

        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            # Map filepath to future
            future_to_filepath = {
                executor.submit(
                    process_file, filepath, file_to_base_map[filepath]
                ): filepath
                for filepath in files_to_process
            }

            for future in as_completed(future_to_filepath):
                filepath = future_to_filepath[future]
                try:
                    result = future.result()
                    if result:
                        relative_path, formatted_string = result
                        # Use resolved path as key temporarily for uniqueness if needed,
                        # but sort by relative path later. Store relative path with content.
                        processed_content[relative_path] = formatted_string
                    else:
                        skipped_count += (
                            1  # File was binary or had other processing error
                        )
                except Exception as e:
                    log.error(f"Error getting result for file {filepath}: {e}")
                    skipped_count += 1
                finally:
                    progress.update(task, advance=1)  # Advance progress bar

    # --- Write Collected Content ---
    log.info(f"Appending content of {len(processed_content)} files...")
    try:
        with open(output_file, "a", encoding="utf-8") as out_f:
            # Sort by relative path for deterministic order before writing
            sorted_items = sorted(
                processed_content.items(), key=lambda item: item[0]
            )
            for relative_path, formatted_string in sorted_items:
                log.debug(f"Writing content for: {relative_path}")
                out_f.write(formatted_string)
    except Exception as e:
        log.error(f"Failed to write processed content to {output_file}: {e}")
        return

    console.print(
        f"[bold green]✓[/] Compilation complete. "
        f"{len(processed_content)} files written to [blue]{output_file}[/]. "
        f"{skipped_count} files skipped (binary/errors)."
    )


if __name__ == "__main__":
    main()
