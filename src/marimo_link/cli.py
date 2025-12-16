import re
import textwrap
from typing import Iterable, Any, Generator, LiteralString
from python_minifier import minify
from cyclopts import App
from pathlib import Path
import ast
import logging

logging.basicConfig(level=logging.DEBUG, format='%(message)s')
logger = logging.getLogger(__name__)

cli_app = App()


def format_return_statements_to_single_line(code: str) -> str:
    """
    Adjusts all multi-line return statements in the given Python code
    so that they span a single line.
    """
    # Matches return statements with multi-line tuples or lists
    return_pattern = re.compile(
        r"^(?P<indent>\s*return\s*\([\s\S]*?\))",  # Match entire multiline return statement
        re.MULTILINE
    )

    def reformat_return(match):
        return_statement = match.group(0)
        # Remove newlines and redundant spaces while keeping the structure
        formatted = re.sub(r"\s*\n\s*", " ", return_statement)  # Merge lines into single line
        formatted = re.sub(r"\s*,\s*", ", ", formatted)         # Ensure single spaces after commas
        return formatted

    # Apply the transformation to all matching return statements
    return return_pattern.sub(reformat_return, code)


def format_function_declarations_to_single_line(code: str) -> str:
    """
    Adjusts all multi-line function signatures in the given Python code
    so that they span a single line.
    """
    # Matches function definitions and captures the multi-line arguments
    function_pattern = re.compile(
        r"^(\s*def\s+\w+\s*\()([^\)]*?)(\):)",
        re.DOTALL | re.MULTILINE
    )

    def reformat_function(match):
        prefix = match.group(1)  # "def function_name("
        arguments = match.group(2)  # The arguments spread across multiple lines
        suffix = match.group(3)  # "):"

        # Remove newlines and ensure spaces between arguments
        single_line_arguments = re.sub(r"\s*,\s*", ", ", arguments.replace("\n", "").strip())
        return f"{prefix}{single_line_arguments}{suffix}"

    # Apply the transformation to all matching function declarations
    return function_pattern.sub(reformat_function, code)


def new_lines(code_lines: list):
    return '\n'.join(code_lines)


def yield_next_function_block(source_code: str) -> Generator[tuple[LiteralString, LiteralString], None, None]:
    """Parse through source code and yield function blocks."""
    formatted_source_code = format_function_declarations_to_single_line(source_code)
    formatted_source_code = format_return_statements_to_single_line(formatted_source_code)
    org_souce_code: list = formatted_source_code.split('\n')
    last_processed_line = 0
    tree = ast.parse(formatted_source_code)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            start_line = node.lineno
            end_line = 0
            for n in ast.walk(node):
                if isinstance(n, ast.Return):
                    end_line = max(end_line, n.lineno)
            if end_line == 0:
                end_line = node.end_lineno
            lines_before_func = org_souce_code[last_processed_line:start_line]
            func_lines = org_souce_code[start_line:end_line - 1]
            last_processed_line = end_line - 1
            logger.debug(f'{start_line=} {last_processed_line=} {end_line=}')
            return_bef, return_aft = new_lines(lines_before_func), new_lines(func_lines)
            if return_bef == '':
                return None
            yield return_bef, return_aft



def mini(source_code):
    result = minify(source=source_code,
                    filename='tmp.py',
                    rename_globals=False,
                    combine_imports=False,
                    rename_locals=True,
                    constant_folding=True,
                    hoist_literals=False,
                    remove_explicit_return_none=True)
    return result


@cli_app.default()
def minify_marimo(input_marimo_file: Path, output_marimo_file: Path):
    """Convert marimo code to a smaller size."""

    org_size = input_marimo_file.stat().st_size
    with output_marimo_file.open('w') as f:
        source_code = input_marimo_file.read_text()
        counter = 0
        for before_func, in_func in list(yield_next_function_block(source_code)):
            counter += 1
            # print(f'{counter:=^20}')
            # print(before_func)
            # print(in_func)
            block_dedent = textwrap.dedent(in_func)
            try:
                mini_dedent = mini(block_dedent)
            except IndentationError as e:
                msg = f'Error within this block: {e}'
                print(f"{msg:=^240}")
                print(block_dedent)
                print('HINT: Ensure functions explicitly returns, e.g. return None')
                raise SystemExit(1)
            mini_indent = textwrap.indent(mini_dedent, prefix='    ')
            # print(before_func)
            # print(mini_indent)
            f.write(f'\n{before_func}')
            f.write(f'\n{mini_indent}')
        f.write('''    return


if __name__ == "__main__":
    app.run()
''')
    new_size = output_marimo_file.stat().st_size
    logger.info(f'Writing output to {output_marimo_file.as_posix()} {1 - (new_size/org_size):.2%} smaller than original.')
    # Path('out.py').write_text(result)


def main():
    cli_app()


if __name__ == "__main__":
    main()