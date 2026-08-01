"""Windows implementation of the visual WeChat session boundary."""

from __future__ import annotations

from datetime import date, datetime
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import threading
import time
import unicodedata
import re

from PIL import ImageGrab

from .desktop_vision import DEFAULT_STATE_ROOT, WeChatDesktopError
from .public_link import canonicalize_public_article_url
from .vision import (
    OCRToken,
    Rect,
    VisionSnapshot,
    extract_article_candidates,
    extract_article_header_date,
    locate_copy_link,
    locate_exact_account,
    locate_network_search,
)


WECHAT_EXE = Path(r"C:\Program Files\Tencent\Weixin\Weixin.exe")
_INPUT_LOCK = threading.Lock()


class WindowsWeChatVisionSession:
    """Drive the logged-in WeChat UI using OCR-confirmed visual states."""

    def __init__(
        self,
        *,
        timeout: float = 20,
        action_pause: float = 0.35,
        diagnostics_root: Path | None = None,
        ocr=None,
    ):
        if not _is_windows():
            raise WeChatDesktopError("Desktop WeChat discovery requires Windows")
        _enable_dpi_awareness()
        self.timeout = max(3, float(timeout))
        self.action_pause = max(0.1, float(action_pause))
        self.diagnostics_root = Path(
            diagnostics_root or DEFAULT_STATE_ROOT / "diagnostics"
        )
        self._ocr = ocr or _build_ocr()
        self._main_handle = 0
        self._account = ""
        self._last_list_fingerprint: tuple[tuple[str, str], ...] = ()

    def open_account_articles(self, account: str) -> None:
        import pyautogui
        import pyperclip

        with _INPUT_LOCK:
            self._account = str(account).strip()
            if not self._account:
                raise ValueError("account is required")
            self._main_handle = self._ensure_logged_in_main_window()
            _show_and_focus(self._main_handle, maximize=True)
            search_snapshot = self._snapshot(
                self._main_handle,
                crop=_top_left_search_crop(_window_rect(self._main_handle)),
            )
            search = _find_token(search_snapshot, "搜索", contains=True)
            if search is not None:
                search_point = search.rect.center
            elif search_snapshot.bounds.width >= 500:
                # A populated search input no longer contains its placeholder.
                # Its position is stable inside the verified main-window header.
                search_point = (
                    search_snapshot.bounds.left + 165,
                    search_snapshot.bounds.top + 95,
                )
            else:
                self._fail("WeChat search box was not found", self._main_handle)
            pyautogui.click(*search_point)
            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("backspace")
            time.sleep(self.action_pause)
            pyperclip.copy(self._account)
            pyautogui.hotkey("ctrl", "v")
            deadline = time.monotonic() + 6
            network_rect = None
            local_crop = _local_search_crop(_window_rect(self._main_handle))
            while time.monotonic() < deadline:
                local = self._snapshot(self._main_handle, crop=local_crop)
                try:
                    network_rect = locate_network_search(local, self._account)
                    break
                except LookupError:
                    time.sleep(0.25)
            if network_rect is None:
                self._fail("WeChat network-search row was not found", self._main_handle)
            pyautogui.click(*network_rect.center)
            results = self._wait_snapshot(self._is_account_results)

            try:
                account_rect = locate_exact_account(results, self._account)
            except LookupError as exc:
                self._fail(str(exc), _foreground_wechat_window(), cause=exc)
            pyautogui.click(*account_rect.center)

            profile = self._wait_snapshot(self._is_account_profile)
            article_tab = _find_token(profile, "文章", exact=True)
            if article_tab is None:
                self._fail("The official-account article tab was not found")
            pyautogui.click(*article_tab.rect.center)
            article_list = self._wait_snapshot(self._has_article_rows)
            self._last_list_fingerprint = _article_fingerprint(article_list)

    def list_visible_articles(self, now: datetime):
        snapshot = self._snapshot(_foreground_wechat_window())
        candidates = extract_article_candidates(snapshot.tokens, now)
        if not candidates:
            self._fail("No dated WeChat article rows were recognized")
        self._last_list_fingerprint = tuple(
            (item.title, item.published_date.isoformat()) for item in candidates
        )
        return candidates

    def open_article(self, candidate) -> None:
        import pyautogui

        pyautogui.click(*candidate.click_rect.center)
        self._wait_snapshot(self._is_open_article)

    def copy_current_link(self) -> tuple[str, date | None]:
        import pyautogui
        import pyperclip

        article = self._snapshot(_foreground_wechat_window())
        header_date = _header_date(article)
        menu_anchor = _find_token(article, "总结由", contains=True)
        if menu_anchor:
            menu_point = (menu_anchor.rect.right + 38, menu_anchor.rect.center[1])
        else:
            bounds = article.bounds
            menu_point = (
                bounds.left + int(bounds.width * 0.87),
                bounds.top + max(24, int(bounds.height * 0.02)),
            )
        previous = str(pyperclip.paste() or "")
        pyautogui.click(*menu_point)
        menu = self._wait_snapshot(
            lambda snapshot: _find_token(snapshot, "复制链接", exact=True) is not None
        )
        try:
            copy_rect = locate_copy_link(menu)
        except LookupError as exc:
            self._fail(str(exc), cause=exc)
        pyautogui.click(*copy_rect.center)

        deadline = time.monotonic() + 5
        last_value = previous
        while time.monotonic() < deadline:
            value = str(pyperclip.paste() or "").strip()
            last_value = value
            try:
                return canonicalize_public_article_url(value), header_date
            except ValueError:
                time.sleep(0.15)
        self._fail(f"WeChat did not copy a public article link: {last_value[:80]}")

    def return_to_articles(self) -> None:
        import pyautogui

        pyautogui.hotkey("ctrl", "w")
        self._wait_snapshot(self._has_article_rows)

    def scroll_articles(self) -> bool:
        import pyautogui

        handle = _foreground_wechat_window()
        before = self._last_list_fingerprint
        bounds = _window_rect(handle)
        pyautogui.moveTo(
            bounds.left + int(bounds.width * 0.52),
            bounds.top + int(bounds.height * 0.78),
        )
        pyautogui.scroll(-7)
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            time.sleep(0.35)
            snapshot = self._snapshot(handle)
            current = _article_fingerprint(snapshot)
            if current and current != before:
                self._last_list_fingerprint = current
                return True
        return False

    def _ensure_logged_in_main_window(self) -> int:
        windows = _wechat_windows()
        if not windows:
            if not WECHAT_EXE.is_file():
                raise WeChatDesktopError(f"WeChat is not installed at {WECHAT_EXE}")
            subprocess.Popen([str(WECHAT_EXE)])
            windows = _wait_for_wechat_windows(self.timeout)
        handle = max(windows, key=lambda item: _window_rect(item).width * _window_rect(item).height)
        _show_and_focus(handle)
        snapshot = self._snapshot(handle)
        enter = _find_token(snapshot, "进入微信", exact=True)
        if enter:
            import pyautogui

            pyautogui.click(*enter.rect.center)
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                candidates = _wechat_windows()
                large = [
                    item
                    for item in candidates
                    if _window_rect(item).width >= 900 and _window_rect(item).height >= 600
                ]
                if large:
                    return max(
                        large,
                        key=lambda item: _window_rect(item).width * _window_rect(item).height,
                    )
                time.sleep(0.3)
            self._fail("WeChat did not enter the already logged-in account", handle)
        if snapshot.bounds.width < 900 or snapshot.bounds.height < 600:
            self._fail(
                "WeChat is not at its logged-in main window; log in once and retry",
                handle,
            )
        return handle

    def _wait_snapshot(self, predicate) -> VisionSnapshot:
        deadline = time.monotonic() + self.timeout
        last_handle = 0
        while time.monotonic() < deadline:
            handle = _foreground_wechat_window(allow_missing=True)
            if handle:
                last_handle = handle
                snapshot = self._snapshot(handle)
                if predicate(snapshot):
                    return snapshot
            time.sleep(0.35)
        self._fail("WeChat UI state did not become ready before timeout", last_handle)

    def _snapshot(self, handle: int, crop: Rect | None = None) -> VisionSnapshot:
        import numpy as np

        bounds = crop or _window_rect(handle)
        image = ImageGrab.grab(
            bbox=(bounds.left, bounds.top, bounds.right, bounds.bottom),
            all_screens=True,
        )
        result, _ = self._ocr(np.asarray(image))
        tokens = []
        for box, text, confidence in result or ():
            score = float(confidence)
            if score < 0.45:
                continue
            left = bounds.left + int(min(point[0] for point in box))
            top = bounds.top + int(min(point[1] for point in box))
            right = bounds.left + int(max(point[0] for point in box))
            bottom = bounds.top + int(max(point[1] for point in box))
            tokens.append(OCRToken(str(text), Rect(left, top, right, bottom), score))
        return VisionSnapshot(bounds, tuple(tokens))

    def _is_account_results(self, snapshot: VisionSnapshot) -> bool:
        has_account_section = _find_token(snapshot, "账号", contains=True) is not None
        try:
            locate_exact_account(snapshot, self._account)
            has_exact = True
        except LookupError:
            has_exact = False
        return has_account_section and has_exact

    def _is_account_profile(self, snapshot: VisionSnapshot) -> bool:
        return (
            _find_token(snapshot, self._account, exact=True) is not None
            and _find_token(snapshot, "文章", exact=True) is not None
        )

    @staticmethod
    def _has_article_rows(snapshot: VisionSnapshot) -> bool:
        return bool(extract_article_candidates(snapshot.tokens))

    @staticmethod
    def _is_open_article(snapshot: VisionSnapshot) -> bool:
        return _header_date(snapshot) is not None or _find_token(
            snapshot, "写留言", contains=True
        ) is not None

    def _fail(self, message: str, handle: int = 0, cause: Exception | None = None):
        handle = handle or _foreground_wechat_window(allow_missing=True)
        if handle:
            try:
                self.diagnostics_root.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                bounds = _window_rect(handle)
                ImageGrab.grab(
                    bbox=(bounds.left, bounds.top, bounds.right, bounds.bottom),
                    all_screens=True,
                ).save(self.diagnostics_root / f"wechat-{stamp}.png")
            except Exception:
                pass
        error = WeChatDesktopError(message)
        if cause:
            raise error from cause
        raise error


def _build_ocr():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise WeChatDesktopError(
            "Install requirements-wechat-ui.txt to enable offline Chinese OCR"
        ) from exc
    return RapidOCR()


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _wechat_windows() -> list[int]:
    import psutil

    handles: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(handle, _):
        if not ctypes.windll.user32.IsWindowVisible(handle):
            return True
        process_id = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
        try:
            executable = psutil.Process(process_id.value).exe().lower()
        except (psutil.Error, OSError):
            return True
        if "\\tencent\\weixin\\" not in executable:
            return True
        rect = _window_rect(handle)
        if rect.width > 200 and rect.height > 150:
            handles.append(int(handle))
        return True

    ctypes.windll.user32.EnumWindows(callback_type(callback), 0)
    return handles


def _wait_for_wechat_windows(timeout: float) -> list[int]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        windows = _wechat_windows()
        if windows:
            return windows
        time.sleep(0.3)
    raise WeChatDesktopError("WeChat did not open before timeout")


def _foreground_wechat_window(allow_missing: bool = False) -> int:
    import psutil

    handle = int(ctypes.windll.user32.GetForegroundWindow())
    if handle:
        process_id = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
        try:
            executable = psutil.Process(process_id.value).exe().lower()
            if "\\tencent\\weixin\\" in executable:
                return handle
        except (psutil.Error, OSError):
            pass
    windows = _wechat_windows()
    if windows:
        return max(windows, key=lambda item: _window_rect(item).width * _window_rect(item).height)
    if allow_missing:
        return 0
    raise WeChatDesktopError("No visible WeChat window was found")


def _window_rect(handle: int) -> Rect:
    raw = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(handle, ctypes.byref(raw)):
        raise WeChatDesktopError("Could not read the WeChat window bounds")
    return Rect(raw.left, raw.top, raw.right, raw.bottom)


def _show_and_focus(handle: int, maximize: bool = False) -> None:
    ctypes.windll.user32.ShowWindow(handle, 3 if maximize else 9)
    ctypes.windll.user32.SetForegroundWindow(handle)
    time.sleep(0.5)


def _top_left_search_crop(bounds: Rect) -> Rect:
    return Rect(
        bounds.left,
        bounds.top,
        min(bounds.right, bounds.left + 600),
        min(bounds.bottom, bounds.top + 240),
    )


def _local_search_crop(bounds: Rect) -> Rect:
    return Rect(
        bounds.left,
        bounds.top,
        min(bounds.right, bounds.left + 1000),
        min(bounds.bottom, bounds.top + 1200),
    )


def _find_token(
    snapshot: VisionSnapshot,
    text: str,
    *,
    exact: bool = False,
    contains: bool = False,
) -> OCRToken | None:
    wanted = _key(text)
    matches = []
    for token in snapshot.tokens:
        candidate = _key(token.text)
        matched = candidate == wanted if exact else wanted in candidate if contains else candidate == wanted
        if matched:
            matches.append(token)
    return max(matches, key=lambda token: token.confidence, default=None)


def _key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", "", normalized).casefold()


def _header_date(snapshot: VisionSnapshot) -> date | None:
    for token in snapshot.tokens:
        parsed = extract_article_header_date(token.text)
        if parsed:
            return parsed
    return None


def _article_fingerprint(snapshot: VisionSnapshot) -> tuple[tuple[str, str], ...]:
    return tuple(
        (item.title, item.published_date.isoformat())
        for item in extract_article_candidates(snapshot.tokens)
    )


def _is_windows() -> bool:
    return hasattr(ctypes, "windll")
