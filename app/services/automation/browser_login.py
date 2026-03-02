"""
Modul login otomatis Gemini (untuk registrasi akun baru)
"""
import os
import json
import random
import string
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from DrissionPage import ChromiumPage, ChromiumOptions


class TaskCancelledError(Exception):
    """Raised when a login task is cancelled."""
    pass


# Konstanta
AUTH_LOGIN_URL = "https://auth.business.gemini.google/login?"
DEFAULT_XSRF_TOKEN = "KdLRzKwwBTD5wo8nUollAbY6cW0"

# Path Chromium umum di Linux
CHROMIUM_PATHS = [
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
]


def _find_chromium_path() -> Optional[str]:
    """Cari path browser Chromium/Chrome yang tersedia"""
    for path in CHROMIUM_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


class GeminiAutomation:
    """Login otomatis Gemini"""

    def __init__(
        self,
        user_agent: str = "",
        proxy: str = "",
        headless: bool = True,
        timeout: int = 60,
        log_callback=None,
    ) -> None:
        self.user_agent = user_agent or self._get_ua()
        self.proxy = proxy
        self.headless = headless
        self.timeout = timeout
        self.log_callback = log_callback
        self._page = None
        self._user_data_dir = None
        self._last_send_error = ""

    def stop(self) -> None:
        """Request stop eksternal: usahakan tutup instance browser."""
        page = self._page
        if page:
            try:
                page.quit()
            except Exception:
                pass

    def login_and_extract(self, email: str, mail_client) -> dict:
        """Eksekusi login dan ekstrak konfigurasi"""
        page = None
        user_data_dir = None
        try:
            page = self._create_page()
            user_data_dir = getattr(page, 'user_data_dir', None)
            self._page = page
            self._user_data_dir = user_data_dir
            return self._run_flow(page, email, mail_client)
        except TaskCancelledError:
            raise
        except Exception as exc:
            self._log("error", f"automation error: {exc}")
            return {"success": False, "error": str(exc)}
        finally:
            if page:
                try:
                    page.quit()
                except Exception:
                    pass
            self._page = None
            self._cleanup_user_data(user_data_dir)
            self._user_data_dir = None

    def _create_page(self) -> ChromiumPage:
        """Buat halaman browser"""
        options = ChromiumOptions()

        # Deteksi otomatis path browser Chromium (Linux/Docker environment)
        chromium_path = _find_chromium_path()
        if chromium_path:
            options.set_browser_path(chromium_path)

        options.set_argument("--incognito")
        options.set_argument("--no-sandbox")
        options.set_argument("--disable-dev-shm-usage")
        options.set_argument("--disable-setuid-sandbox")
        options.set_argument("--disable-blink-features=AutomationControlled")
        options.set_argument("--window-size=1280,800")
        options.set_user_agent(self.user_agent)

        # Pengaturan bahasa Indonesia
        options.set_argument("--lang=id-ID")
        options.set_pref("intl.accept_languages", "id-ID,id,en")

        if self.proxy:
            options.set_argument(f"--proxy-server={self.proxy}")

        if self.headless:
            # Gunakan headless mode versi baru, lebih mirip browser asli
            options.set_argument("--headless=new")
            options.set_argument("--disable-gpu")
            options.set_argument("--no-first-run")
            options.set_argument("--disable-extensions")
            # 
            options.set_argument("--disable-infobars")
            options.set_argument("--enable-features=NetworkService,NetworkServiceInProcess")

        options.auto_port()
        page = ChromiumPage(options)
        page.set.timeouts(self.timeout)

        # ：
        if self.headless:
            try:
                page.run_cdp("Page.addScriptToEvaluateOnNewDocument", source="""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
                    window.chrome = {runtime: {}};

                    // 
                    Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 1});
                    Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
                    Object.defineProperty(navigator, 'vendor', {get: () => 'Google Inc.'});

                    //  headless 
                    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                    Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

                    //  permissions
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({state: Notification.permission}) :
                            originalQuery(parameters)
                    );
                """)
            except Exception:
                pass

        return page

    def _run_flow(self, page, email: str, mail_client) -> dict:
        """Execute the full Gemini Enterprise registration flow.

        Flow (March 2026):
        1. Open https://auth.business.gemini.google/login?
        2. Fill email address + click "Continue with email"
        3. Wait for verification page (accountverification.business.gemini.google)
           - 6 individual input boxes for the code
        4. Poll generator.email for OTP code
        5. Enter code in the 6 boxes + click "Verify"
        6. Handle "Try Business edition at no cost" page (name + Agree & get started)
        7. Handle "Get answers from your data" popup (I'll do this later)
        8. Extract cookies & config from business.gemini.google
        """
        from datetime import datetime

        # =============================================
        # Step 1: Open login page
        # =============================================
        self._log("info", f"🌐 Opening login page for: {email}")
        page.get(AUTH_LOGIN_URL, timeout=self.timeout)
        time.sleep(3)

        current_url = page.url
        self._log("info", f"📍 Current URL: {current_url}")

        # Check if already logged in
        if "business.gemini.google" in current_url and "csesidx=" in current_url and "/cid/" in current_url:
            self._log("info", "✅ Already logged in, extracting config")
            return self._extract_config(page, email)

        # =============================================
        # Step 2: Fill email and click "Continue with email"
        # =============================================
        self._log("info", "📧 Filling email address...")

        # Find email input field
        email_input = None
        email_selectors = [
            "css:input[type='email']",
            "css:input[placeholder*='mail' i]",
            "css:input[placeholder*='Email' i]",
            "css:input[name='email']",
            "css:input[type='text']",
        ]
        for selector in email_selectors:
            try:
                email_input = page.ele(selector, timeout=3)
                if email_input:
                    self._log("info", f"✅ Email input found: {selector}")
                    break
            except Exception:
                continue

        if not email_input:
            self._log("error", "❌ Email input not found on login page")
            self._save_screenshot(page, "email_input_missing")
            return {"success": False, "error": "email input not found"}

        # Type email with human-like input
        email_input.click()
        time.sleep(0.3)
        if not self._simulate_human_input(email_input, email):
            email_input.input(email, clear=True)
        time.sleep(0.5)

        # Click "Continue with email" button
        self._log("info", "🖱️ Clicking 'Continue with email'...")
        continue_btn = None
        continue_selectors = [
            "css:button[type='submit']",
        ]
        for selector in continue_selectors:
            try:
                continue_btn = page.ele(selector, timeout=3)
                if continue_btn:
                    break
            except Exception:
                continue

        if not continue_btn:
            # Fallback: find button by text
            try:
                buttons = page.eles("tag:button")
                for btn in buttons:
                    text = (btn.text or "").strip().lower()
                    if "continue" in text or "email" in text or "sign in" in text:
                        continue_btn = btn
                        break
            except Exception:
                pass

        if not continue_btn:
            self._log("error", "❌ 'Continue with email' button not found")
            self._save_screenshot(page, "continue_button_missing")
            return {"success": False, "error": "continue button not found"}

        continue_btn.click()
        send_time = datetime.now()
        self._log("info", "✅ Continue button clicked, waiting for verification page...")
        time.sleep(5)

        # =============================================
        # Step 3: Wait for verification page
        # =============================================
        current_url = page.url
        self._log("info", f"📍 Current URL: {current_url}")

        # Wait up to 15s for the verification page to load
        for i in range(30):
            current_url = page.url
            if "verify-oob-code" in current_url or "verification" in current_url:
                self._log("info", "✅ Verification page loaded")
                break
            time.sleep(0.5)
        else:
            # Check if we're already past verification
            if "business.gemini.google" in current_url and "csesidx=" in current_url:
                return self._extract_config(page, email)
            self._log("error", f"❌ Verification page not reached. URL: {current_url}")
            self._save_screenshot(page, "verify_page_not_reached")
            return {"success": False, "error": f"verification page not reached: {current_url}"}

        time.sleep(2)

        # =============================================
        # Step 4: Wait for code input boxes to appear
        # =============================================
        self._log("info", "⏳ Waiting for code input boxes...")
        code_inputs = self._wait_for_code_inputs(page)
        if not code_inputs:
            self._log("error", "❌ Code input boxes not found")
            self._save_screenshot(page, "code_inputs_missing")
            return {"success": False, "error": "code input boxes not found"}

        self._log("info", f"✅ Found {len(code_inputs)} code input boxes")

        # =============================================
        # Step 5: Poll for OTP code from email
        # =============================================
        self._log("info", "📬 Polling for verification code...")
        if hasattr(mail_client, 'set_browser_driver'):
            mail_client.set_browser_driver(page, driver_type="dp")

        code = mail_client.poll_for_code(timeout=90, interval=10, since_time=send_time)

        if not code:
            # Try resend code
            self._log("warning", "⚠️ No code received, clicking Resend code...")
            if self._click_resend_code_button(page):
                send_time = datetime.now()
                time.sleep(3)
                if hasattr(mail_client, 'set_browser_driver'):
                    mail_client.set_browser_driver(page, driver_type="dp")
                code = mail_client.poll_for_code(timeout=60, interval=10, since_time=send_time)

            if not code:
                self._log("error", "❌ Verification code not found after resend")
                self._save_screenshot(page, "code_timeout")
                return {"success": False, "error": "verification code timeout"}

        self._log("info", f"✅ Got verification code: {code}")

        # =============================================
        # Step 6: Enter code in the 6 input boxes + click Verify
        # =============================================
        self._log("info", "⌨️ Entering verification code...")
        
        # Re-find code inputs (tab may have changed)
        code_inputs = self._wait_for_code_inputs(page, timeout=5)
        if not code_inputs:
            self._log("error", "❌ Code inputs disappeared")
            return {"success": False, "error": "code inputs disappeared after polling"}

        # Enter each character into its respective box
        success = self._enter_code_in_boxes(page, code_inputs, code)
        if not success:
            self._log("error", "❌ Failed to enter code in boxes")
            return {"success": False, "error": "failed to enter code"}

        time.sleep(1)

        # Click "Verify" button
        self._log("info", "🖱️ Clicking Verify button...")
        verify_btn = self._find_button_by_text(page, ["verify", "verifikasi", "submit"])
        if verify_btn:
            verify_btn.click()
        else:
            # Fallback: submit via Enter key on last input
            self._log("warning", "⚠️ Verify button not found, pressing Enter...")
            try:
                code_inputs[-1].input("\n")
            except Exception:
                pass

        # Wait for page to navigate away from verification
        self._log("info", "⏳ Waiting for verification result...")
        old_url = page.url
        for i in range(60):  # 30 seconds max
            time.sleep(0.5)
            current_url = page.url
            if current_url != old_url and "verify-oob-code" not in current_url:
                self._log("info", f"✅ Verification succeeded! URL: {current_url}")
                break
            if i > 0 and i % 8 == 0:
                self._log("info", f"⏳ Still waiting... ({i // 2}s)")
        else:
            current_url = page.url
            if "verify-oob-code" in current_url:
                self._log("error", "❌ Verification failed (still on verify page)")
                self._save_screenshot(page, "verification_failed")
                return {"success": False, "error": "verification code rejected"}

        time.sleep(3)

        # =============================================
        # Step 7: Handle "Try Business edition" signup page
        # =============================================
        current_url = page.url
        self._log("info", f"📍 Post-verification URL: {current_url}")
        self._handle_agreement_page(page)

        # =============================================
        # Step 8: Handle "Get answers from your data" popup
        # =============================================
        self._handle_data_popup(page)

        # =============================================
        # Step 9: Navigate to dashboard & extract config
        # =============================================
        current_url = page.url
        has_business_params = "business.gemini.google" in current_url and "csesidx=" in current_url and "/cid/" in current_url

        if has_business_params:
            self._log("info", "🎊 Login berhasil! Extracting config...")
            return self._extract_config(page, email)

        # If not on dashboard yet, navigate there
        if "business.gemini.google" not in current_url:
            self._log("info", "🌐 Navigating to business.gemini.google...")
            page.get("https://business.gemini.google/", timeout=self.timeout)
            time.sleep(5)

        # Handle any remaining setup pages
        current_url = page.url
        if "/admin/create" in current_url:
            self._handle_agreement_page(page)
            time.sleep(3)

        # Handle username setup if needed
        if "cid" not in page.url:
            if self._handle_username_setup(page):
                time.sleep(5)

        # Handle popup again (may appear after navigation)
        self._handle_data_popup(page)

        # Wait for URL with business params
        if not self._wait_for_business_params(page):
            page.refresh()
            time.sleep(5)
            self._handle_data_popup(page)
            if not self._wait_for_business_params(page):
                self._log("error", "❌ Business params not found in URL")
                self._save_screenshot(page, "params_missing")
                return {"success": False, "error": "URL parameters not found"}

        self._log("info", "🎊 Login berhasil! Extracting config...")
        return self._extract_config(page, email)

    def _click_send_code_button(self, page) -> bool:
        """Legacy: Click send code button (kept for resend compatibility)."""
        time.sleep(2)
        max_send_attempts = 5
        resend_delay_seconds = 10

        # Try "Continue with email" or "Send code" button
        keywords = ["continue", "email", "Send code", "Send verification", "Verification code"]
        try:
            buttons = page.eles("tag:button")
            for btn in buttons:
                text = (btn.text or "").strip()
                if text and any(kw.lower() in text.lower() for kw in keywords):
                    for attempt in range(1, max_send_attempts + 1):
                        try:
                            btn.click()
                            time.sleep(3)
                            # Check if we navigated to verification page
                            if "verify" in page.url.lower() or "verification" in page.url.lower():
                                return True
                            if attempt < max_send_attempts:
                                self._log("warning", f"⚠️ Retry... ({attempt}/{max_send_attempts})")
                                time.sleep(resend_delay_seconds)
                        except Exception as e:
                            self._log("warning", f"⚠️ Click error: {e}")
                    return False
        except Exception as e:
            self._log("warning", f"⚠️ Button search error: {e}")

        return False


    def _wait_for_code_inputs(self, page, timeout: int = 30):
        """Wait for the 6 individual code input boxes on the verification page.

        The verification page at accountverification.business.gemini.google
        has 6 separate input boxes for the verification code.
        """
        for attempt in range(timeout // 2):
            try:
                # Try various selectors for the individual input boxes
                inputs = (
                    page.eles("css:input[type='text']", timeout=1) or
                    page.eles("css:input[type='tel']", timeout=1) or
                    page.eles("css:input[autocomplete='one-time-code']", timeout=1) or
                    page.eles("css:input[maxlength='1']", timeout=1)
                )
                # Filter to only small single-char inputs (the 6 code boxes)
                code_inputs = []
                for inp in inputs:
                    try:
                        maxlen = inp.attr("maxlength")
                        input_type = inp.attr("type") or ""
                        # Code boxes typically have maxlength=1 or are type=text/tel
                        if maxlen == "1" or (input_type in ("text", "tel") and len(code_inputs) < 6):
                            code_inputs.append(inp)
                    except Exception:
                        code_inputs.append(inp)

                if len(code_inputs) >= 6:
                    return code_inputs[:6]

                # Also try to find a single input that accepts the full code
                single_input = (
                    page.ele("css:input[jsname='ovqh0b']", timeout=1) or
                    page.ele("css:input[name='pinInput']", timeout=1) or
                    page.ele("css:input[autocomplete='one-time-code']", timeout=1)
                )
                if single_input:
                    return [single_input]  # Wrap in list for compatibility

            except Exception:
                pass
            time.sleep(2)
        return None

    def _enter_code_in_boxes(self, page, code_inputs: list, code: str) -> bool:
        """Enter verification code into input boxes.

        Handles both:
        - 6 individual boxes (one char each)
        - Single input box (all chars at once)
        """
        try:
            if len(code_inputs) == 1:
                # Single input box — type all at once
                inp = code_inputs[0]
                inp.click()
                time.sleep(0.3)
                if not self._simulate_human_input(inp, code):
                    inp.input(code, clear=True)
                return True

            # 6 individual boxes
            if len(code) < len(code_inputs):
                self._log("error", f"❌ Code length ({len(code)}) < boxes ({len(code_inputs)})")
                return False

            for i, inp in enumerate(code_inputs):
                char = code[i] if i < len(code) else ""
                try:
                    inp.click()
                    time.sleep(random.uniform(0.05, 0.15))
                    inp.input(char)
                    time.sleep(random.uniform(0.08, 0.2))
                except Exception as e:
                    self._log("warning", f"⚠️ Input box {i+1} error: {e}")
                    # Try alternative: just type into first box (some UIs auto-advance)
                    if i == 0:
                        return False
                    continue

            self._log("info", f"✅ Entered {len(code)} chars into {len(code_inputs)} boxes")
            return True
        except Exception as e:
            self._log("error", f"❌ Enter code error: {e}")
            return False

    def _find_button_by_text(self, page, keywords: list, timeout: int = 5):
        """Find a button by matching text content."""
        try:
            # First try submit button
            submit_btn = page.ele("css:button[type='submit']", timeout=2)
            if submit_btn:
                text = (submit_btn.text or "").strip().lower()
                for kw in keywords:
                    if kw.lower() in text:
                        return submit_btn

            # Then search all buttons
            buttons = page.eles("tag:button", timeout=timeout)
            for btn in buttons:
                text = (btn.text or "").strip().lower()
                for kw in keywords:
                    if kw.lower() in text:
                        return btn

            # Try link elements too (some buttons are <a> tags)
            links = page.eles("tag:a", timeout=2)
            for link in links:
                text = (link.text or "").strip().lower()
                for kw in keywords:
                    if kw.lower() in text:
                        return link
        except Exception:
            pass
        return None

    def _simulate_human_input(self, element, text: str) -> bool:
        """（，）

        Args:
            element: 
            text: 

        Returns:
            bool: 
        """
        try:
            # 
            element.click()
            time.sleep(random.uniform(0.1, 0.3))

            # 
            for char in text:
                element.input(char)
                # ：（50-150ms/）
                time.sleep(random.uniform(0.05, 0.15))

            # 
            time.sleep(random.uniform(0.2, 0.5))
            return True
        except Exception:
            return False

    def _click_resend_code_button(self, page) -> bool:
        """Click 'Resend code' button/link on verification page."""
        time.sleep(2)
        try:
            # Look for "Resend code" link or button
            resend = self._find_button_by_text(page, ["resend"])
            if resend:
                self._log("info", "🔄 Clicking 'Resend code'...")
                resend.click()
                time.sleep(3)
                return True
        except Exception:
            pass

        return False

    def _handle_agreement_page(self, page) -> None:
        """Handle 'Try Business edition at no cost for 30 days' signup page.

        This page has:
        - "First and last name" / "Full name" input field
        - "Agree & get started" button
        """
        time.sleep(2)
        current_url = page.url

        # Check if we're on an agreement/signup/admin page
        page_text = ""
        try:
            page_text = (page.ele("tag:body").text or "").lower()
        except Exception:
            pass

        is_agreement = (
            "/admin/create" in current_url or
            "try business" in page_text or
            "agree" in page_text or
            "get started" in page_text or
            "full name" in page_text or
            "first and last name" in page_text
        )

        if not is_agreement:
            return

        self._log("info", "📋 Agreement page detected: 'Try Business edition at no cost'")

        # Step 1: Fill name input
        name_input = None
        name_selectors = [
            "css:input[placeholder*='name' i]",
            "css:input[placeholder*='Full name' i]",
            "css:input[aria-label*='name' i]",
            "css:input[type='text']",
        ]

        for selector in name_selectors:
            try:
                name_input = page.ele(selector, timeout=2)
                if name_input:
                    self._log("info", f"✅ Found name input: {selector}")
                    break
            except Exception:
                continue

        if name_input:
            from faker import Faker
            try:
                fake = Faker()
                full_name = fake.name()
            except Exception:
                suffix = "".join(random.choices(string.ascii_letters, k=4))
                full_name = f"Alex {suffix.capitalize()}"

            self._log("info", f"⌨️ Filling name: {full_name}")
            name_input.click()
            time.sleep(0.3)
            if not self._simulate_human_input(name_input, full_name):
                name_input.input(full_name, clear=True)
            time.sleep(0.5)
        else:
            self._log("warning", "⚠️ Name input not found, continuing...")

        # Step 2: Click "Agree & get started" button
        agree_btn = self._find_button_by_text(page, ["agree", "get started"])
        if agree_btn:
            self._log("info", f"✅ Clicking '{(agree_btn.text or '').strip()}'...")
            agree_btn.click()
            self._log("info", "⏳ Waiting for sign-in process...")
            time.sleep(8)  # Sign-in takes a few seconds
        else:
            # Fallback: try submit button
            submit_btn = page.ele("css:button[type='submit']", timeout=2)
            if submit_btn:
                self._log("info", "✅ Clicking submit button (fallback)")
                submit_btn.click()
                time.sleep(8)
            else:
                self._log("warning", "⚠️ No agreement button found, continuing...")

    def _handle_data_popup(self, page) -> None:
        """Handle 'Get answers from your data' popup.

        This popup appears after first login with:
        - "Get answers from your data"
        - "I'll do this later" link/button
        - "Connect my data" button
        """
        time.sleep(2)
        try:
            # Look for "I'll do this later" button/link
            later_btn = self._find_button_by_text(page, [
                "do this later",
                "i'll do this later",
                "later",
                "skip",
            ])
            if later_btn:
                self._log("info", "🖱️ Clicking 'I'll do this later' on data popup...")
                later_btn.click()
                time.sleep(2)
                return

            # Also check for dialog/modal dismiss
            try:
                dismiss_btns = page.eles("css:button[aria-label*='close' i]", timeout=2)
                for btn in dismiss_btns:
                    btn.click()
                    self._log("info", "✅ Closed popup via close button")
                    time.sleep(1)
                    return
            except Exception:
                pass

        except Exception as e:
            self._log("info", f"No data popup found (this is OK): {e}")

    def _wait_for_cid(self, page, timeout: int = 10) -> bool:
        """URLcid"""
        for _ in range(timeout):
            if "cid" in page.url:
                return True
            time.sleep(1)
        return False

    def _wait_for_business_params(self, page, timeout: int = 30) -> bool:
        """（csesidx  cid）"""
        for _ in range(timeout):
            url = page.url
            if "csesidx=" in url and "/cid/" in url:
                return True
            time.sleep(1)
        return False

    def _handle_username_setup(self, page) -> bool:
        """"""
        current_url = page.url

        if "auth.business.gemini.google/login" in current_url:
            return False

        selectors = [
            "css:input[type='text']",
            "css:input[name='displayName']",
            "css:input[aria-label*='' i]",
            "css:input[aria-label*='display name' i]",
        ]

        username_input = None
        for selector in selectors:
            try:
                username_input = page.ele(selector, timeout=2)
                if username_input:
                    break
            except Exception:
                continue

        if not username_input:
            return False

        suffix = "".join(random.choices(string.ascii_letters + string.digits, k=3))
        username = f"Test{suffix}"

        try:
            # 
            username_input.click()
            time.sleep(0.2)
            username_input.clear()
            time.sleep(0.1)

            # ，
            if not self._simulate_human_input(username_input, username):
                username_input.input(username)
                time.sleep(0.3)

            buttons = page.eles("tag:button")
            submit_btn = None
            for btn in buttons:
                text = (btn.text or "").strip().lower()
                if any(kw in text for kw in ["", "", "", "submit", "continue", "confirm", "save", "", "", "next"]):
                    submit_btn = btn
                    break

            if submit_btn:
                submit_btn.click()
            else:
                username_input.input("\n")

            time.sleep(5)
            return True
        except Exception:
            return False

    def _extract_config(self, page, email: str) -> dict:
        """Ekstrak konfigurasi"""
        try:
            if "cid/" not in page.url:
                page.get("https://business.gemini.google/", timeout=self.timeout)
                time.sleep(3)

            url = page.url
            if "cid/" not in url:
                return {"success": False, "error": "cid not found"}

            config_id = url.split("cid/")[1].split("?")[0].split("/")[0]
            csesidx = url.split("csesidx=")[1].split("&")[0] if "csesidx=" in url else ""

            cookies = page.cookies()
            ses = next((c["value"] for c in cookies if c["name"] == "__Secure-C_SES"), None)
            host = next((c["value"] for c in cookies if c["name"] == "__Host-C_OSES"), None)

            ses_obj = next((c for c in cookies if c["name"] == "__Secure-C_SES"), None)
            # ，（Cookie expiry  UTC ）
            beijing_tz = timezone(timedelta(hours=8))
            if ses_obj and "expiry" in ses_obj:
                #  UTC ，12
                cookie_expire_beijing = datetime.fromtimestamp(ses_obj["expiry"], tz=beijing_tz)
                expires_at = (cookie_expire_beijing - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
            else:
                expires_at = (datetime.now(beijing_tz) + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")

            config = {
                "id": email,
                "csesidx": csesidx,
                "config_id": config_id,
                "secure_c_ses": ses,
                "host_c_oses": host,
                "expires_at": expires_at,
            }
            return {"success": True, "config": config}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _save_screenshot(self, page, name: str) -> None:
        """Save screenshot for debugging."""
        try:
            screenshot_dir = os.path.join("/app", "data", "automation")
            os.makedirs(screenshot_dir, exist_ok=True)
            path = os.path.join(screenshot_dir, f"{name}_{int(time.time())}.png")
            page.get_screenshot(path=path)
        except Exception:
            pass

    def _log(self, level: str, message: str) -> None:
        """"""
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except TaskCancelledError:
                raise
            except Exception:
                pass

    def _cleanup_user_data(self, user_data_dir: Optional[str]) -> None:
        """"""
        if not user_data_dir:
            return
        try:
            import shutil
            if os.path.exists(user_data_dir):
                shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass

    @staticmethod
    def _get_ua() -> str:
        """User-Agent"""
        v = random.choice(["120.0.0.0", "121.0.0.0", "122.0.0.0"])
        return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v} Safari/537.36"
