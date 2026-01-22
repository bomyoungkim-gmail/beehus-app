from dataclasses import dataclass
from selenium.webdriver.common.by import By


@dataclass(frozen=True)
class SeletorJefferies:
    """Selectors for the Jefferies portal."""

    URL_BASE = "https://jefferies.netxinvestor.com/nxi/welcome?timedOut=true&isMfe=true&isModern=true"

    # Cookies
    COOKIES_ACCEPT = (By.ID, "onetrust-accept-btn-handler")

    # Login
    LOGIN_OPEN_BTN = (By.CSS_SELECTOR, "button[aria-label='Login']")
    LOGIN_OPEN_BTN_TEXT = (By.XPATH, "//button[.//span[normalize-space()='Login']]")
    USER_ID = (By.ID, "userid")
    PASSWORD = (By.ID, "password")
    LOGIN_SUBMIT = (By.ID, "loginButton1")

    # OTP
    CONTACT_METHOD = (By.CSS_SELECTOR, "mat-select[name='selectedContact']")
    CONTACT_METHOD_OPTION = (By.XPATH, "//mat-option//span[normalize-space()='Beehus by Email']")
    SEND_CODE = (By.ID, "reqOTPButton")
    OTP_INPUT = (By.ID, "otp")
    VERIFY_OTP = (By.ID, "verifyOTP")

    # Holdings
    NAV_ACCOUNTS = (By.CSS_SELECTOR, "a.nav-accounts")
    NAV_HOLDINGS = (By.ID, "nav-holdings")
    SHOWING_SELECT = (By.CSS_SELECTOR, "mat-select[aria-label^='Showing']")
    PRIOR_CLOSE_OPTION = (By.XPATH, "//mat-option//span[normalize-space()='Prior Close']")
    DOWNLOAD_BTN = (By.CSS_SELECTOR, "button[aria-label='Download']")
    EXPORT_EXCEL = (By.CSS_SELECTOR, "button[aria-label='Export to Excel']")

    # History
    NAV_HISTORY = (By.ID, "nav-history")
    TIME_PERIOD = (By.ID, "timeperiod")
    PREV_BUSINESS_DAY = (By.XPATH, "//mat-option//span[normalize-space()='Previous Business Day']")
    APPLY_FILTERS = (By.XPATH, "//button[.//span[normalize-space()='Apply Filters']]")

    # Logout
    USER_MENU = (By.CSS_SELECTOR, "button[aria-label='Settings and Logout']")
    LOGOUT_BTN = (By.XPATH, "//button[.//span[normalize-space()='Logout']]")
