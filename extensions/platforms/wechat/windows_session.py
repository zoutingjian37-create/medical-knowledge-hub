"""Windows implementation of the visual WeChat session boundary."""

from __future__ import annotations

from datetime import date, datetime
import ctypes
from ctypes import wintypes
from difflib import SequenceMatcher
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
    extract_article_tab_candidates,
    extract_date_headers,
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
        self._web_handle = 0
        self._last_snapshot_handle = 0
        self._account = ""
        self._last_list_fingerprint: tuple[tuple[str, str], ...] = ()
        self._visible_candidates = ()
        self._continuation_date: date | None = None
        self._step = "startup"

    def open_account_articles(self, account: str) -> None:
        import pyautogui
        import pyperclip

        with _INPUT_LOCK:
            self._step = "search_account"
            self._account = str(account).strip()
            self._continuation_date = None
            if not self._account:
                raise ValueError("account is required")
            _close_stale_web_windows()
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
            network_rect = None
            for _attempt in range(2):
                _show_and_focus(self._main_handle, maximize=True)
                pyautogui.click(*search_point)
                pyautogui.hotkey("ctrl", "a")
                pyautogui.press("backspace")
                time.sleep(self.action_pause)
                pyperclip.copy(self._account)
                pyautogui.hotkey("ctrl", "v")
                deadline = time.monotonic() + 4
                local_crop = _local_search_crop(_window_rect(self._main_handle))
                while time.monotonic() < deadline:
                    local = self._snapshot(self._main_handle, crop=local_crop)
                    try:
                        network_rect = locate_network_search(local, self._account)
                        break
                    except LookupError:
                        time.sleep(0.25)
                if network_rect is not None:
                    break
                # Restore and re-read the search box before the second try;
                # minimized Qt windows can discard the first synthetic focus.
                search_snapshot = self._snapshot(
                    self._main_handle,
                    crop=_top_left_search_crop(_window_rect(self._main_handle)),
                )
                search = _find_token(search_snapshot, "搜索", contains=True)
                if search is not None:
                    search_point = search.rect.center
            if network_rect is None:
                self._fail("WeChat network-search row was not found", self._main_handle)
            pyautogui.click(*network_rect.center)
            results = self._wait_snapshot(self._is_account_results, kind="web")
            self._web_handle = self._last_snapshot_handle

            self._step = "open_profile"
            try:
                account_rect = locate_exact_account(results, self._account)
            except LookupError as exc:
                self._fail(str(exc), self._web_handle, cause=exc)
            last_used = _find_token(results, "上次使用", contains=True)
            profile = None
            for attempt, target in enumerate(
                tuple(
                    item
                    for item in (
                        last_used.rect if last_used is not None else None,
                        account_rect,
                    )
                    if item is not None
                )
            ):
                if attempt:
                    pyautogui.doubleClick(*target.center, interval=0.1)
                else:
                    pyautogui.click(*target.center)
                profile = self._wait_snapshot_optional(
                    self._is_account_profile,
                    handle=self._web_handle,
                    timeout=8,
                )
                if profile is not None:
                    break
            if profile is None:
                self._fail(
                    "The exact official account was found but its profile did not open",
                    self._web_handle,
                )
            self._step = "select_article_tab"
            article_tab = _find_token(profile, "文章", exact=True)
            if article_tab is None:
                self._fail("The official-account article tab was not found")
            article_list = None
            for attempt in range(3):
                if attempt:
                    profile = self._snapshot(self._web_handle)
                    article_tab = _find_token(profile, "文章", exact=True)
                    if article_tab is None:
                        break
                if attempt == 1:
                    pyautogui.doubleClick(*article_tab.rect.center, interval=0.1)
                else:
                    pyautogui.click(*article_tab.rect.center)
                article_list = self._wait_snapshot_optional(
                    self._has_article_tab_rows,
                    handle=self._web_handle,
                    timeout=6,
                )
                if article_list is not None:
                    break
            if article_list is None:
                self._fail(
                    "The official-account profile opened but the article tab did not activate",
                    self._web_handle,
                )
            self._visible_candidates = extract_article_tab_candidates(
                article_list.tokens
            )
            self._last_list_fingerprint = _article_tab_fingerprint(article_list)
            self._step = "article_list"

    def list_visible_articles(self, now: datetime):
        self._step = "navigate_dates"
        snapshot = self._snapshot(self._active_web_handle())
        candidates = extract_article_tab_candidates(snapshot.tokens, now)
        if not candidates:
            self._fail("No dated WeChat article rows were recognized")
        self._visible_candidates = candidates
        self._last_list_fingerprint = tuple(
            (item.title, item.published_date.isoformat()) for item in candidates
        )
        return candidates

    def open_article(self, candidate) -> None:
        import pyautogui

        self._step = "open_article"
        current = _match_candidate(self._visible_candidates, candidate)
        if current is None:
            # WeChat repaints lazy-loaded rows after a tab closes.  OCR can
            # observe one incomplete frame, so retry a few fresh frames
            # before declaring that the row truly moved.
            for _ in range(3):
                snapshot = self._snapshot(self._active_web_handle())
                self._visible_candidates = extract_article_tab_candidates(
                    snapshot.tokens
                )
                current = _match_candidate(self._visible_candidates, candidate)
                if current is not None:
                    break
                time.sleep(0.25)
        if current is None:
            self._fail(
                f"The article row moved before it could be opened: {candidate.title}",
                self._active_web_handle(),
            )
        handle = self._active_web_handle()
        bounds = _window_rect(handle)
        if _candidate_needs_top_reveal(current, bounds):
            # A coarse PageDown can leave the first row underneath WeChat's
            # sticky tab header. Move over the document and nudge upward so
            # the complete title becomes an actionable link, then re-OCR it.
            for _ in range(2):
                pyautogui.moveTo(
                    bounds.left + int(bounds.width * 0.55),
                    bounds.top + int(bounds.height * 0.45),
                )
                pyautogui.scroll(2)
                time.sleep(self.action_pause)
                snapshot = self._snapshot(handle)
                self._visible_candidates = extract_article_tab_candidates(
                    snapshot.tokens
                )
                refreshed = _match_candidate(self._visible_candidates, candidate)
                if refreshed is not None:
                    current = refreshed
                if not _candidate_needs_top_reveal(current, bounds):
                    break
        pyautogui.click(*current.click_rect.center)
        self._wait_snapshot(self._is_open_article, handle=handle)

    def copy_current_link(self) -> tuple[str, date | None]:
        import pyautogui
        import pyperclip

        self._step = "copy_link"
        article = self._snapshot(self._active_web_handle())
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
            lambda snapshot: _find_token(snapshot, "复制链接", exact=True) is not None,
            handle=self._active_web_handle(),
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

        self._step = "return_to_list"
        pyautogui.hotkey("ctrl", "w")
        snapshot = self._wait_snapshot(
            self._has_article_tab_rows,
            handle=self._active_web_handle(),
        )
        self._visible_candidates = extract_article_tab_candidates(snapshot.tokens)
        self._last_list_fingerprint = tuple(
            (item.title, item.published_date.isoformat())
            for item in self._visible_candidates
        )
        self._step = "article_list"

    def recover_to_article_list(self) -> bool:
        """Restore the current account's list without repeating its search."""

        import pyautogui

        self._step = "return_to_list"
        try:
            handle = self._active_web_handle()
            snapshot = self._snapshot(handle)
            if self._has_article_tab_rows(snapshot):
                self._remember_article_list(snapshot)
                return True
            if self._is_open_article(snapshot):
                pyautogui.hotkey("ctrl", "w")
                snapshot = self._wait_snapshot_optional(
                    self._has_article_tab_rows,
                    handle=handle,
                    timeout=6,
                )
                if snapshot is not None:
                    self._remember_article_list(snapshot)
                    return True
            profile = self._snapshot(handle)
            article_tab = _find_token(profile, "文章", exact=True)
            if article_tab is None:
                return False
            pyautogui.click(*article_tab.rect.center)
            snapshot = self._wait_snapshot_optional(
                self._has_article_tab_rows,
                handle=handle,
                timeout=6,
            )
            if snapshot is None:
                return False
            self._remember_article_list(snapshot)
            return True
        except (RuntimeError, OSError, LookupError):
            return False

    def _remember_article_list(self, snapshot: VisionSnapshot) -> None:
        self._visible_candidates = extract_article_tab_candidates(snapshot.tokens)
        self._last_list_fingerprint = tuple(
            (item.title, item.published_date.isoformat())
            for item in self._visible_candidates
        )
        self._step = "article_list"

    def scroll_articles(self, steps: int = 1) -> bool:
        import pyautogui

        self._step = "navigate_dates"
        if not isinstance(steps, int) or steps == 0:
            raise ValueError("steps must be a non-zero integer")
        handle = self._active_web_handle()
        before = self._last_list_fingerprint
        _ensure_foreground(handle)
        key, presses = _scroll_command(steps)
        # PageDown/PageUp targets the focused article document reliably. Mouse
        # wheel events are ignored by some WeChatAppEx builds unless a row is
        # clicked first, which risks opening an article by accident.
        pyautogui.press(key, presses=presses, interval=0.08)
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            time.sleep(0.35)
            snapshot = self._snapshot(handle)
            current_candidates = extract_article_tab_candidates(snapshot.tokens)
            current = tuple(
                (item.title, item.published_date.isoformat())
                for item in current_candidates
            )
            if current and current != before:
                self._visible_candidates = current_candidates
                self._last_list_fingerprint = current
                return True
        return False

    def _ensure_logged_in_main_window(self) -> int:
        windows = _wechat_windows(kind="main", include_hidden=True)
        if not windows:
            if not WECHAT_EXE.is_file():
                raise WeChatDesktopError(f"WeChat is not installed at {WECHAT_EXE}")
            subprocess.Popen([str(WECHAT_EXE)])
            windows = _wait_for_wechat_windows(self.timeout, kind="main")
        handle = max(windows, key=lambda item: _window_rect(item).width * _window_rect(item).height)
        # A minimized or tray-restored Qt window can report compact bounds until
        # it is maximized.  Validate the logged-in layout only after restoration.
        _show_and_focus(handle, maximize=True)
        snapshot = self._snapshot(handle)
        enter = _find_token(snapshot, "进入微信", exact=True)
        if enter:
            import pyautogui

            pyautogui.click(*enter.rect.center)
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                candidates = _wechat_windows(kind="main", include_hidden=True)
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

    def _wait_snapshot(
        self,
        predicate,
        *,
        kind: str | None = None,
        handle: int = 0,
    ) -> VisionSnapshot:
        deadline = time.monotonic() + self.timeout
        last_handle = 0
        while time.monotonic() < deadline:
            candidate = handle or _foreground_wechat_window(
                allow_missing=True, kind=kind
            )
            if candidate and ctypes.windll.user32.IsWindow(candidate):
                last_handle = candidate
                snapshot = self._snapshot(candidate)
                if predicate(snapshot):
                    self._last_snapshot_handle = candidate
                    return snapshot
            time.sleep(0.35)
        self._fail("WeChat UI state did not become ready before timeout", last_handle)

    def _wait_snapshot_optional(
        self,
        predicate,
        *,
        handle: int = 0,
        timeout: float = 5,
    ) -> VisionSnapshot | None:
        deadline = time.monotonic() + max(0.5, float(timeout))
        while time.monotonic() < deadline:
            candidate = handle or _foreground_wechat_window(allow_missing=True)
            if candidate and ctypes.windll.user32.IsWindow(candidate):
                snapshot = self._snapshot(candidate)
                if predicate(snapshot):
                    self._last_snapshot_handle = candidate
                    return snapshot
            time.sleep(0.3)
        return None

    def _active_web_handle(self) -> int:
        if self._web_handle and ctypes.windll.user32.IsWindow(self._web_handle):
            return self._web_handle
        self._web_handle = _foreground_wechat_window(kind="web")
        return self._web_handle

    def _snapshot(self, handle: int, crop: Rect | None = None) -> VisionSnapshot:
        import numpy as np

        _ensure_foreground(handle)
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

    def _has_article_rows(self, snapshot: VisionSnapshot) -> bool:
        return bool(
            extract_article_candidates(
                snapshot.tokens,
                inherited_date=self._continuation_date,
            )
        )

    @staticmethod
    def _has_article_tab_rows(snapshot: VisionSnapshot) -> bool:
        return bool(extract_article_tab_candidates(snapshot.tokens))

    def _remember_visible_date(
        self,
        snapshot: VisionSnapshot,
        now: datetime | None = None,
    ) -> None:
        headers = extract_date_headers(snapshot.tokens, now)
        if headers:
            self._continuation_date = headers[-1][0]

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
        local_steps = {
            "navigate_dates",
            "open_article",
            "copy_link",
            "return_to_list",
        }
        error = WeChatDesktopError(
            message,
            step=self._step,
            retry_from=(
                "article_list" if self._step in local_steps else "account_search"
            ),
            progress_kept=self._step in local_steps,
        )
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


def _wechat_process_kind(
    executable: str,
    ancestor_executables: tuple[str, ...] = (),
) -> str | None:
    """Classify only the two top-level process families used by WeChat 4.x."""

    name = Path(str(executable or "")).name.casefold()
    if name == "weixin.exe":
        return "main"
    ancestor_names = {
        Path(str(item or "")).name.casefold() for item in ancestor_executables
    }
    if name == "wechatappex.exe" and "weixin.exe" in ancestor_names:
        return "web"
    return None


def _process_identity(process_id: int) -> tuple[str, tuple[str, ...]]:
    import psutil

    process = psutil.Process(process_id)
    executable = process.exe()
    ancestors: list[str] = []
    for parent in process.parents()[:8]:
        try:
            ancestors.append(parent.exe())
        except (psutil.Error, OSError):
            continue
    return executable, tuple(ancestors)


def _should_include_wechat_window(
    kind: str,
    *,
    visible: bool,
    iconic: bool = False,
    width: int,
    height: int,
    include_hidden: bool = False,
    class_name: str = "",
    title: str = "",
) -> bool:
    is_main_shell = (
        kind == "main"
        and "qwindowicon" in class_name.casefold()
        and title.strip() == "微信"
    )
    if iconic and include_hidden and is_main_shell:
        return True
    if width <= 200 or height <= 150:
        return False
    if visible:
        return True
    return (
        include_hidden
        and is_main_shell
        and width >= 900
        and height >= 600
    )


def _wechat_windows(
    kind: str | None = None,
    *,
    include_hidden: bool = False,
) -> list[int]:
    import psutil

    handles: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(handle, _):
        visible = bool(ctypes.windll.user32.IsWindowVisible(handle))
        process_id = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
        try:
            executable, ancestors = _process_identity(process_id.value)
        except (psutil.Error, OSError):
            return True
        process_kind = _wechat_process_kind(executable, ancestors)
        if process_kind is None or (kind is not None and process_kind != kind):
            return True
        rect = _window_rect(handle)
        class_buffer = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(handle, class_buffer, 256)
        title_buffer = ctypes.create_unicode_buffer(512)
        ctypes.windll.user32.GetWindowTextW(handle, title_buffer, 512)
        if _should_include_wechat_window(
            process_kind,
            visible=visible,
            iconic=bool(ctypes.windll.user32.IsIconic(handle)),
            width=rect.width,
            height=rect.height,
            include_hidden=include_hidden,
            class_name=class_buffer.value,
            title=title_buffer.value,
        ):
            handles.append(int(handle))
        return True

    ctypes.windll.user32.EnumWindows(callback_type(callback), 0)
    return handles


def _wait_for_wechat_windows(timeout: float, kind: str | None = None) -> list[int]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        windows = _wechat_windows(kind=kind)
        if windows:
            return windows
        time.sleep(0.3)
    raise WeChatDesktopError("WeChat did not open before timeout")


def _foreground_wechat_window(
    allow_missing: bool = False,
    kind: str | None = None,
) -> int:
    import psutil

    handle = int(ctypes.windll.user32.GetForegroundWindow())
    if handle:
        process_id = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
        try:
            executable, ancestors = _process_identity(process_id.value)
            process_kind = _wechat_process_kind(executable, ancestors)
            if process_kind is not None and (kind is None or process_kind == kind):
                return handle
        except (psutil.Error, OSError):
            pass
    windows = _wechat_windows(kind=kind)
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
    try:
        from pywinauto import Desktop

        window = Desktop(backend="win32").window(handle=handle)
        if maximize:
            window.maximize()
        elif ctypes.windll.user32.IsIconic(handle):
            window.restore()
        window.set_focus()
    except Exception:
        ctypes.windll.user32.ShowWindow(handle, 3 if maximize else 9)
        ctypes.windll.user32.SetForegroundWindow(handle)
    time.sleep(0.5)


def _ensure_foreground(handle: int) -> None:
    if int(ctypes.windll.user32.GetForegroundWindow()) == int(handle):
        return
    _show_and_focus(handle)
    deadline = time.monotonic() + 0.8
    while time.monotonic() < deadline:
        if int(ctypes.windll.user32.GetForegroundWindow()) == int(handle):
            return
        time.sleep(0.05)
    raise WeChatDesktopError("Could not focus the intended WeChat window")


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


def _match_candidate(candidates, target):
    """Resolve a row again after WeChat repaints the article list."""

    same_date = [
        item for item in candidates if item.published_date == target.published_date
    ]
    if not same_date:
        # A repaint can temporarily attach the neighboring date label to a
        # row.  Rebind only when the normalized title is an unambiguous near
        # exact match; the opened article header remains authoritative.
        wanted = _key(target.title)
        ranked = sorted(
            (
                SequenceMatcher(None, wanted, _key(item.title)).ratio(),
                item,
            )
            for item in candidates
        )
        if not ranked:
            return None
        best_score, best = ranked[-1]
        second_score = ranked[-2][0] if len(ranked) > 1 else 0.0
        return best if best_score >= 0.72 and best_score - second_score >= 0.12 else None
    wanted = _key(target.title)
    exact = next((item for item in same_date if _key(item.title) == wanted), None)
    if exact is not None:
        return exact
    scored = [
        (SequenceMatcher(None, wanted, _key(item.title)).ratio(), item)
        for item in same_date
    ]
    score, best = max(scored, key=lambda pair: pair[0])
    return best if score >= 0.72 else None


def _candidate_needs_top_reveal(candidate, bounds: Rect) -> bool:
    """Detect a row whose title is covered by the sticky profile header."""

    sticky_bottom = bounds.top + max(
        180,
        min(250, int(bounds.height * 0.18)),
    )
    return candidate.click_rect.center[1] <= sticky_bottom


def _article_fingerprint(
    snapshot: VisionSnapshot,
    *,
    inherited_date: date | None = None,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (item.title, item.published_date.isoformat())
        for item in extract_article_candidates(
            snapshot.tokens,
            inherited_date=inherited_date,
        )
    )


def _article_tab_fingerprint(
    snapshot: VisionSnapshot,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (item.title, item.published_date.isoformat())
        for item in extract_article_tab_candidates(snapshot.tokens)
    )


def _is_windows() -> bool:
    return hasattr(ctypes, "windll")


def _close_stale_web_windows() -> None:
    """Close public-content browser windows left behind by an earlier run."""

    if not _is_windows():
        return
    handles = _wechat_windows(kind="web", include_hidden=True)
    for handle in handles:
        ctypes.windll.user32.PostMessageW(handle, 0x0010, 0, 0)  # WM_CLOSE
    if not handles:
        return
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if not _wechat_windows(kind="web", include_hidden=True):
            return
        time.sleep(0.1)


def _scroll_command(steps: int) -> tuple[str, int]:
    if not isinstance(steps, int) or steps == 0:
        raise ValueError("steps must be a non-zero integer")
    return ("pagedown" if steps > 0 else "pageup", abs(steps))
