import os
import signal
import subprocess
from typing import Sequence
from playwright.sync_api import Playwright, sync_playwright, expect
import pyperclip
import time
from loguru import logger

PORT = 5678
MARIMO_MAX_SIZE = 32_000  # This may change in the future, but what I've discovered today


def make_marimo_url_read_only(org_url: str) -> str:
    """
    Generates a read-only Marimo URL from the provided organizational URL.

    This function extracts the code portion from the given organizational
    URL and constructs a new URL suitable for embedding in read-only mode.

    :param org_url: The original organizational URL containing the
        code segment after the '#code/' part.
    :type org_url: str
    :return: A constructed URL that enables the Marimo app in read-only
        mode with specific settings for embedding.
    :rtype: str
    """
    code = org_url.split('#code/')[-1]
    prefix_url = 'https://marimo.app?mode=read&embed=true&include-code=false&show-chrome=false&code='
    output_url = prefix_url + code
    return output_url


def web_get_url_to_clipboard(playwright: Playwright) -> None:
    """
    Launches a Firefox browser via Playwright to navigate to a specified local URL, interact
    with certain elements on the page to create and handle a WebAssembly link, and then
    shuts down the session.

    :param playwright: An instance of the Playwright object, used to control browser automation.
    :type playwright: Playwright
    :return: None
    """
    browser = playwright.firefox.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{PORT}/")
    page.get_by_test_id("notebook-menu-dropdown").click()
    page.get_by_test_id("notebook-menu-dropdown-Share").click()
    page.get_by_text("Create WebAssembly link").click()
    page.get_by_test_id("shutdown-button").click()
    page.get_by_role("button", name="Confirm Shutdown").click()
    page.close()

    # ---------------------
    context.close()
    browser.close()


def start_subprocess_and_get_pid(
    cmd: Sequence[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> int:
    """Start a subprocess and return its process ID (PID).

    Args:
        cmd: Command and arguments, e.g. ["python", "-c", "print('hi')"].
        cwd: Optional working directory for the subprocess.
        env: Optional environment overrides for the subprocess.

    Returns:
        The PID of the started subprocess.
    """
    proc = subprocess.Popen(
        list(cmd),
        cwd=cwd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # avoid tying lifetime to the parent terminal/session
    )
    return proc.pid


def kill_process_id(pid: int, *, timeout_s: float = 2.0) -> None:
    """Terminate a process by PID.

    Tries a graceful termination first, then force-kills if the process is still
    alive after `timeout_s`.

    Args:
        pid: Process ID to terminate.
        timeout_s: Seconds to wait after SIGTERM before sending SIGKILL.

    Returns:
        None.
    """
    if pid <= 0:
        raise ValueError("pid must be a positive integer")

    # First try graceful termination.
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return  # already gone
    except PermissionError as e:
        raise PermissionError(f"No permission to terminate pid={pid}") from e

    # Wait until it exits (polling via signal 0).
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            os.kill(pid, 0)  # doesn't kill; checks existence/permission
        except ProcessLookupError:
            return  # exited
        except PermissionError as e:
            raise PermissionError(f"No permission to check/terminate pid={pid}") from e
        time.sleep(0.05)

    # Still alive: force kill.
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except PermissionError as e:
        raise PermissionError(f"No permission to force-kill pid={pid}") from e


def open_marimo_file_and_return_pid(marimo_file_path: str) -> int:
    return start_subprocess_and_get_pid(["uvx", "marimo", "edit", "--headless", "--sandbox", "--no-token", "--port", f"{PORT}", marimo_file_path])


def get_marimo_url(input_marimo_file_path: str) -> str:
    """
    Extracts the URL from a Marimo file, modifies it to a read-only format, and copies the updated
    URL back to the clipboard. The function launches a headless browser to retrieve a Marimo URL,
    shuts down the associated process after extracting the URL, and logs data about the URL.

    :param input_marimo_file_path: Path to the Marimo file to be opened
    :type input_marimo_file_path: str
    :return: Updated Marimo URL in a read-only format
    :rtype: str
    """
    logger.info(f"Opening marimo file: {input_marimo_file_path}")
    pid = open_marimo_file_and_return_pid(input_marimo_file_path)

    time.sleep(5)

    logger.info("Opening headless browser and copying URL to clipboard")
    with sync_playwright() as playwright:
        web_get_url_to_clipboard(playwright)

    time.sleep(2)
    logger.info("Shutting down marimo")
    kill_process_id(pid)
    url = pyperclip.paste()
    logger.info(f"Copied marimo URL to clipboard: {url}")
    updated_url = make_marimo_url_read_only(url)
    logger.info(f'Copying updated URL to clipboard: {updated_url}')
    pyperclip.copy(updated_url)
    current_url_size = len(url.encode("utf-8"))
    logger.info(f"URL size: {current_url_size} bytes {current_url_size / MARIMO_MAX_SIZE:.2%} of max size (?) of {MARIMO_MAX_SIZE} bytes")
    return updated_url
