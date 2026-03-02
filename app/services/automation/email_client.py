"""
Generator.email Client
Email provider tanpa API - menggunakan generator.email
"""

import random
import re
import string
import time
from typing import Optional


class GeneratorEmailClient:
    """
    Client untuk generator.email
    Generate email tanpa API, baca OTP langsung dari web via browser driver
    """

    def __init__(
        self,
        domains: list = None,
        proxy: str = "",
        log_callback=None,
    ) -> None:
        self.base_url = "https://generator.email"
        self.domains = domains or ["yourdomain.com"]  # Setup your own domain with MX record!
        self.log_callback = log_callback
        
        self.email: Optional[str] = None
        self.username: Optional[str] = None
        self.domain: Optional[str] = None
        self.password: str = ""  # Generator.email tidak perlu password
        
        # Browser driver (akan di-set dari automation)
        self._browser_driver = None
        self._driver_type = None  # "dp" atau "uc"

    def _log(self, level: str, message: str):
        """Log callback"""
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except Exception:
                pass

    def set_credentials(self, email: str, password: str = "") -> None:
        """Set credentials (untuk kompatibilitas interface)"""
        self.email = email
        self.password = password

    def set_browser_driver(self, driver, driver_type: str = "dp"):
        """
        Set browser driver untuk akses web
        driver_type: "dp" (DrissionPage) atau "uc" (undetected-chromedriver)
        """
        self._browser_driver = driver
        self._driver_type = driver_type
        self._log("info", f"🌐 Browser driver set: {driver_type}")

    def generate_random_username(self, length: int = 10) -> str:
        """Generate random username"""
        chars = string.ascii_lowercase + string.digits
        return "".join(random.choices(chars, k=length))

    def register_account(self, domain: Optional[str] = None) -> bool:
        """Generate email baru (tanpa API call)"""
        try:
            # Pilih domain
            self.domain = domain or random.choice(self.domains)
            
            # Generate username random
            self.username = self.generate_random_username()
            self.email = f"{self.username}@{self.domain}"
            
            self._log("info", f"✅ Email generated: {self.email}")
            self._log("info", f"🌐 Check email di: {self.base_url}/{self.email}")
            
            return True
            
        except Exception as e:
            self._log("error", f"❌ Gagal generate email: {e}")
            return False

    def poll_for_code(
        self,
        timeout: int = 120,
        interval: int = 5,
        since_time=None,
    ) -> Optional[str]:
        """
        Tunggu dan ambil kode verifikasi dari email
        Menggunakan browser driver untuk akses web
        """
        if not self.email:
            self._log("error", "❌ Email belum dibuat!")
            return None
        
        if not self._browser_driver:
            self._log("error", "❌ Browser driver tidak tersedia!")
            self._log("error", "   Pastikan set_browser_driver() sudah dipanggil dari automation")
            return None
        
        url = f"{self.base_url}/{self.email}"
        max_retries = timeout // interval
        
        self._log("info", f"⏱️ Polling OTP dari generator.email (timeout: {timeout}s, interval: {interval}s, max: {max_retries} retries)")
        self._log("info", f"🌐 URL: {url}")
        
        for attempt in range(1, max_retries + 1):
            self._log("info", f"🔄 Percobaan #{attempt}/{max_retries} - Cek email...")
            
            try:
                code = self._fetch_code_from_web(url)
                if code:
                    self._log("info", f"🎉 Kode verifikasi ditemukan: {code}")
                    return code
                
                if attempt < max_retries:
                    self._log("info", f"⏳ Belum ada email, tunggu {interval} detik...")
                    time.sleep(interval)
                    
            except Exception as e:
                self._log("error", f"❌ Error saat cek email: {e}")
                if attempt < max_retries:
                    time.sleep(interval)
        
        self._log("error", f"⏰ Timeout! Tidak dapat kode verifikasi dalam {timeout} detik")
        return None

    def _fetch_code_from_web(self, url: str) -> Optional[str]:
        """
        Fetch kode verifikasi dari web menggunakan browser driver
        """
        try:
            if self._driver_type == "dp":
                # DrissionPage
                return self._fetch_code_drissionpage(url)
            elif self._driver_type == "uc":
                # Undetected-chromedriver (Selenium)
                return self._fetch_code_selenium(url)
            else:
                self._log("error", f"❌ Driver type tidak dikenal: {self._driver_type}")
                return None
                
        except Exception as e:
            self._log("error", f"❌ Error fetch code from web: {e}")
            return None

    def _fetch_code_drissionpage(self, url: str) -> Optional[str]:
        """Fetch code menggunakan DrissionPage"""
        page = self._browser_driver
        
        # Simpan tab/window saat ini
        original_tab = page.latest_tab
        
        try:
            # Buka tab baru
            self._log("info", "📂 Buka tab baru untuk cek email...")
            page.new_tab(url)
            new_tab = page.latest_tab
            
            # Tunggu page load
            time.sleep(3)
            
            # Scroll down to ensure email body is visible/loaded
            # generator.email shows ads at top, email body is below
            try:
                new_tab.scroll.to_bottom()
                time.sleep(1)
                new_tab.scroll.to_top()
                time.sleep(1)
            except Exception:
                pass
            
            # Ambil HTML content
            html_content = new_tab.html
            
            # First try: look for verification-code class directly via DOM
            try:
                code_el = new_tab.ele('css:.verification-code', timeout=3)
                if code_el:
                    code_text = (code_el.text or "").strip()
                    if code_text and 4 <= len(code_text) <= 8 and code_text.replace(" ", "").isalnum():
                        code = code_text.replace(" ", "").upper()
                        self._log("info", f"✅ Code from DOM .verification-code: {code}")
                        return code
            except Exception:
                pass
            
            # Second try: look inside mess_bodiyy container
            try:
                email_container = new_tab.ele('css:.mess_bodiyy', timeout=2)
                if email_container:
                    container_html = email_container.html
                    code = self._extract_code_from_html(container_html)
                    if code:
                        self._log("info", f"✅ Code from mess_bodiyy container")
                        return code
            except Exception:
                pass
            
            # Third try: full page HTML extraction
            code = self._extract_code_from_html(html_content)
            
            if code:
                self._log("info", f"✅ Code found in full page")
                return code
            
            # Jika belum ketemu, coba cari email list dan klik detail
            try:
                email_items = (
                    new_tab.eles('css:.email-item') or
                    new_tab.eles('css:.message-item') or  
                    new_tab.eles('css:tr') or
                    new_tab.eles('css:.mail-item')
                )
                
                for item in email_items[:5]:
                    text = item.text.lower()
                    if 'google' in text or 'verification' in text or 'verify' in text:
                        self._log("info", f"📧 Email Google ditemukan, coba klik...")
                        item.click()
                        time.sleep(2)
                        
                        html_content = new_tab.html
                        code = self._extract_code_from_html(html_content)
                        if code:
                            return code
            except Exception as e:
                self._log("info", f"Info: {e}")
            
            return None
            
        finally:
            # Tutup tab baru dan kembali ke tab original
            try:
                if new_tab != original_tab:
                    new_tab.close()
                    page.set.tab(original_tab)
            except Exception:
                pass

    def _fetch_code_selenium(self, url: str) -> Optional[str]:
        """Fetch code menggunakan Selenium (undetected-chromedriver)"""
        driver = self._browser_driver
        
        # Simpan window handle saat ini
        original_window = driver.current_window_handle
        
        try:
            # Buka tab/window baru
            self._log("info", "📂 Buka tab baru untuk cek email...")
            driver.execute_script(f"window.open('{url}', '_blank');")
            
            # Switch ke window baru
            all_windows = driver.window_handles
            new_window = [w for w in all_windows if w != original_window][0]
            driver.switch_to.window(new_window)
            
            # Tunggu page load
            time.sleep(3)
            
            # Ambil HTML content
            html_content = driver.page_source
            
            # Extract code
            code = self._extract_code_from_html(html_content)
            
            if code:
                self._log("info", f"✅ Code found in page")
                return code
            
            # Jika belum ketemu, coba cari dan klik email detail
            try:
                from selenium.webdriver.common.by import By
                
                # Cari email items
                selectors = [
                    (By.CLASS_NAME, "email-item"),
                    (By.CLASS_NAME, "message-item"),
                    (By.TAG_NAME, "tr"),
                ]
                
                for by, selector in selectors:
                    try:
                        items = driver.find_elements(by, selector)
                        for item in items[:5]:  # Cek 5 email terbaru
                            text = item.text.lower()
                            if 'google' in text or 'verification' in text or 'verify' in text:
                                self._log("info", f"📧 Email Google ditemukan, coba klik...")
                                item.click()
                                time.sleep(2)
                                
                                # Cek lagi
                                html_content = driver.page_source
                                code = self._extract_code_from_html(html_content)
                                if code:
                                    return code
                        break  # Jika selector ketemu, break
                    except Exception:
                        continue
            except Exception as e:
                self._log("info", f"Info: {e}")
            
            return None
            
        finally:
            # Tutup window baru dan kembali ke original
            try:
                driver.close()
                driver.switch_to.window(original_window)
            except Exception:
                pass

    def _extract_code_from_html(self, html: str) -> Optional[str]:
        """Extract verification code dari HTML content.

        Gemini Enterprise sends a 6-char uppercase alphanumeric code
        (e.g. YGCRAS) inside a styled box after the text
        "Your one-time verification code is:".

        We first isolate the Google email body to avoid false-positives
        from generator.email page chrome / ads.
        """
        if not html:
            return None

        import re

        # --- PRIORITY 0: Direct CSS class target (generator.email specific) ---
        # generator.email renders code in: <span class="verification-code">YGCRAS</span>
        direct_match = re.search(
            r'<span[^>]*class="[^"]*verification-code[^"]*"[^>]*>\s*([A-Z0-9\s]{4,20})\s*</span>',
            html, re.IGNORECASE | re.DOTALL,
        )
        if direct_match:
            code = re.sub(r'\s+', '', direct_match.group(1)).upper()
            if code and len(code) >= 5 and len(code) <= 8:
                self._log("info", f"✅ OTP dari verification-code class: {code}")
                return code

        # --- Step 0: Isolate the Google email body ---
        # generator.email wraps email in <div class="mess_bodiyy">
        # Fall back to regex if class not found
        email_body = html
        
        # Try mess_bodiyy container first (generator.email specific)
        bodiyy_match = re.search(
            r'<div[^>]*class="[^"]*mess_bodiyy[^"]*"[^>]*>(.*?)</div>\s*<div[^>]*class="[^"]*border',
            html, re.IGNORECASE | re.DOTALL,
        )
        if bodiyy_match:
            email_body = bodiyy_match.group(1)
            self._log("info", "📧 Isolated email from mess_bodiyy container")
        else:
            # Fallback: look for Google-specific markers
            google_section = re.search(
                r'(?:noreply-googlecloud|Gemini\s+Enterprise|verification\s+code)'
                r'.*?'
                r'(?:Google\s+Team|Google\s+LLC|</table>)',
                html,
                re.IGNORECASE | re.DOTALL,
            )
            if google_section:
                email_body = google_section.group(0)
                self._log("info", "📧 Isolated Google email section for code extraction")

        # Strip HTML tags from the email body for text matching
        text = re.sub(r'<[^>]+>', ' ', email_body)
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        # PRIORITY 1: Exact context match — "verification code is: XXXXXX"
        context_patterns = [
            r"verification\s+code\s+is[:\s.]+([A-Z0-9]{5,8})\b",
            r"one-time\s+(?:verification\s+)?code\s+is[:\s.]+([A-Z0-9]{5,8})\b",
            r"Your\s+(?:one-time\s+)?(?:verification\s+)?code\s+is[:\s.]+([A-Z0-9]{5,8})\b",
            r"(?:code|kode|OTP|verifikasi)[:\s]+([A-Z0-9]{5,8})\b",
        ]

        for pattern in context_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                code = match.group(1).upper()
                if self._is_valid_code(code):
                    self._log("info", f"✅ OTP dari context: {code}")
                    return code

        # PRIORITY 2: Prominent styled box in email HTML
        # Google puts the code in a <td> or <div> with background/letter-spacing
        otp_box_patterns = [
            # Code inside styled td (common Google pattern)
            r'<td[^>]*style="[^"]*(?:background|letter-spacing|font-size:\s*2)[^"]*"[^>]*>\s*([A-Z0-9 ]{5,20})\s*</td>',
            r'<div[^>]*style="[^"]*(?:background|letter-spacing|font-size:\s*2)[^"]*"[^>]*>\s*([A-Z0-9 ]{5,20})\s*</div>',
            # Code inside bold/strong (common in simple emails)
            r'<b>\s*([A-Z0-9]{5,8})\s*</b>',
            r'<strong>\s*([A-Z0-9]{5,8})\s*</strong>',
        ]

        for pattern in otp_box_patterns:
            matches = re.finditer(pattern, email_body, re.IGNORECASE | re.DOTALL)
            for match in matches:
                raw = match.group(1).strip()
                # Remove spaces (Google sometimes adds letter-spacing)
                code = re.sub(r'\s+', '', raw).upper()
                if len(code) >= 5 and len(code) <= 8 and self._is_valid_code(code):
                    self._log("info", f"✅ OTP dari styled box: {code}")
                    return code

        # PRIORITY 3: Isolated 6-char code on its own line in email section ONLY
        # Only search within the isolated email body, not the whole page
        if google_section:
            standalone = re.findall(r'(?:^|\s)([A-Z0-9]{6})(?:\s|$)', text)
            for candidate in standalone:
                code = candidate.upper()
                if self._is_valid_code(code):
                    self._log("info", f"⚠️ OTP standalone in email: {code}")
                    return code

        self._log("warning", "❌ No verification code found in email content")
        return None

    def _is_valid_code(self, code: str) -> bool:
        """Validasi apakah code valid (bukan false positive)"""
        if not code or len(code) < 5 or len(code) > 8:
            return False

        import re

        # Must be alphanumeric only
        if not re.match(r'^[A-Z0-9]+$', code, re.IGNORECASE):
            return False

        # Skip CSS units / color codes
        if re.match(r"^\d+(?:PX|PT|EM|REM|VH|VW|PC|FF|CC|EE|AA|BB|DD)$", code, re.IGNORECASE):
            return False

        # Skip hex color codes (e.g. FF0000, E8F0FE)
        if re.match(r'^[0-9A-F]{6}$', code) and not re.search(r'[G-Z]', code, re.IGNORECASE):
            # Pure hex without any G-Z letters — likely a color code, skip
            # But codes like YGCRAS have non-hex letters, so they pass
            pass  # Allow it — could be a valid code too

        # Skip common false positives (HTML/CSS/JS keywords, page chrome words)
        false_positives = {
            "SCRIPT", "IFRAME", "BUTTON", "CLICKS", "MAILTO", "HTTPS",
            "GOOGLE", "VERIFY", "CHROME", "WINDOW", "MARGIN", "BORDER",
            "WEBKIT", "INLINE", "HEADER", "FOOTER", "CENTER", "BUYAPP",
            "RETURN", "SCREEN", "SCROLL", "HIDDEN", "NORMAL", "ITALIC",
            "FAMILY", "WEIGHT", "STYLES", "IMAGES", "COLORS", "LAYOUT",
            "MOBILE", "PLUGIN", "COOKIE", "ACCEPT", "RELOAD", "SUBMIT",
            "DELETE", "CANCEL", "SEARCH", "DOMAIN", "SERVER", "IMPORT",
            "FILTER", "EXPAND", "TOGGLE", "OBJECT", "STRING", "MASTER",
            "SELECT", "INSERT", "UPDATE", "RANDOM", "EXPORT", "MODULE",
            "STATIC", "PUBLIC", "SINCER",  # "Sincerely" truncated
        }
        if code.upper() in false_positives:
            return False

        return True
