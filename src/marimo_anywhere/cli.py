import re
import textwrap
from typing import Generator, LiteralString, Annotated
from uuid import uuid4

import platformdirs
from python_minifier import minify as code_minify
from cyclopts import App
from pathlib import Path
import ast
from loguru import logger

from marimo_anywhere.web import get_marimo_url

cli_app = App()


def format_return_statements_to_single_line(code: str) -> str:
    """
    Reformats multi-line `return` statements containing tuples or lists into a single-line format
    while preserving their structure and readability.

    This function identifies multi-line `return` statements, particularly those that span
    multiple lines due to tuples or lists, and converts them into a single-line equivalent.
    Unnecessary newlines and excessive spaces are removed, ensuring concise and consistent
    output without altering the semantics of the code.

    :param code: The source code as a string to process for formatting multi-line `return` statements.
    :type code: str

    :return: A string with all multi-line `return` statements reformatted into single-line statements.
    :rtype: str
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
    Reformats multi-line Python function declarations in the provided code into a single-line format.
    This function identifies all function definitions with arguments spread across multiple lines
    and converts them into a compact single-line representation while preserving the original
    spacing around the arguments.

    :param code: The Python code to be processed as a string.
    :type code: str
    :return: The reformatted code with function declarations updated to single-line format.
    :rtype: str
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
    """
    Yields the next block of source code function definitions and their respective
    return statement blocks from the given source code. The function transforms
    multi-line function declarations and return statements into single lines for
    easier processing before parsing them and separating blocks.

    :param source_code: The complete source code as a string to be analyzed and
        split into function blocks and return statement blocks.
    :type source_code: str
    :return: A generator yielding tuples, where the first element represents the lines
        of code before the function definition, and the second element represents
        the lines containing the function itself and associated return statement
        lines.
    :rtype: Generator[tuple[LiteralString, LiteralString], None, None]
    """
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
    """
    Minifies the given Python source code to reduce size while preserving its
    functionality. The function applies optimization techniques such as
    constant folding, local variable renaming, and removal of unnecessary
    `None` returns.

    :param source_code: The input Python source code as a string.
    :type source_code: str
    :return: Optimized and minified Python source code as a string.
    :rtype: str
    """
    result = code_minify(source=source_code,
                    filename='tmp.py',
                    rename_globals=False,
                    combine_imports=False,
                    rename_locals=True,
                    constant_folding=True,
                    hoist_literals=False,
                    remove_explicit_return_none=True)
    return result


def random_name(suffix: str = "") -> str:
    return f"{uuid4().hex}.{suffix}"


@cli_app.command()
def minify_to_file(input_marimo_file: Path, output_marimo_file: Path | None = None, whitelist_expression: list[str] = None) -> Annotated[Path, 'output_marimo_file']:
    """Minify a Marimo source file while preserving its behavior.

    Reads `input_marimo_file`, minifies eligible code blocks, and writes the result
    to `output_marimo_file`. You can optionally provide expressions to exclude from
    minimization.

    Args:
        input_marimo_file: Path to the input Marimo source file.
        output_marimo_file: Path where the minified output will be written.
        whitelist_expression: Expressions to exclude from minimization, supports regex. If `None`,
            no expressions are whitelisted.

    Returns:
        None. The minified code is written to `output_marimo_file`.
    """

    if not output_marimo_file:
        temp_dir = platformdirs.user_cache_dir('marimo_anywhere')
        temp_fn = random_name('py')
        output_marimo_file = Path(temp_dir) / temp_fn

    org_size = input_marimo_file.stat().st_size
    with output_marimo_file.open('w') as f:
        source_code = input_marimo_file.read_text()
        counter = 0
        for before_func, in_func in list(yield_next_function_block(source_code)):
            counter += 1
            output_code_block = in_func
            if whitelist_expression is not None:
                block_dedent = textwrap.dedent(in_func)
                for expr in whitelist_expression:
                    found = re.match(expr, block_dedent, re.DOTALL | re.IGNORECASE)
                    if found:
                        logger.info(f'Whitelisted expression found in block {counter}: {expr}')
                        break
                else:
                    try:
                        mini_dedent = mini(block_dedent)
                    except IndentationError as e:
                        msg = f'Error within this block: {e}'
                        print(f"{msg:=^240}")
                        print(block_dedent)
                        print('HINT: Ensure functions explicitly returns, e.g. return None')
                        raise SystemExit(1)
                    mini_indent = textwrap.indent(mini_dedent, prefix='    ')
                    output_code_block = mini_indent
            f.write(f'\n{before_func}')
            f.write(f'\n{output_code_block}')
        f.write('''    return


if __name__ == "__main__":
    app.run()
''')
    new_size = output_marimo_file.stat().st_size
    logger.info(f'Writing output to {output_marimo_file.as_posix()} {1 - (new_size/org_size):.2%} smaller than original.')
    return output_marimo_file


@cli_app.command()
def minify_to_url(input_marimo_file: Path, whitelist_expression: list[str] = None):
    """
    Minifies the given Marimo file to a reduced version based on the whitelist
    expression and converts it to a shareable Marimo URL.

    :param input_marimo_file: Path to the input Marimo configuration file to be minified.
    :type input_marimo_file: Path
    :param whitelist_expression: A list of expressions to whitelist during the minification
        process. Optional.
    :type whitelist_expression: list[str] | None
    :return: A string representing the URL of the minified Marimo configuration file.
    :rtype: str
    """
    minified_file = minify_to_file(input_marimo_file, whitelist_expression=whitelist_expression)
    get_marimo_url(minified_file.as_posix())


def main():
    cli_app()


if __name__ == "__main__":
    main()