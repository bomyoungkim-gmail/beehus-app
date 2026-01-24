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
    USER_ID_ALT = (
        By.CSS_SELECTOR,
        "input[name='userid'], input[aria-labelledby='userIDLabel'], "
        "input[placeholder*='User ID'], input[placeholder*='email']",
    )
    PASSWORD = (By.ID, "password")
    LOGIN_SUBMIT = (By.ID, "loginButton1")
    OVERLAY_BACKDROP = (By.CSS_SELECTOR, "div.cdk-overlay-backdrop")
    LOGIN_DIALOG = (By.CSS_SELECTOR, "mat-dialog-container, div.mat-dialog-container")

    # OTP
    CONTACT_METHOD = (By.CSS_SELECTOR, "mat-select[name='selectedContact']")
    CONTACT_METHOD_OPTION = (By.XPATH, "//mat-option//span[normalize-space()='Beehus by Email']")
    SEND_CODE = (By.ID, "reqOTPButton")
    OTP_INPUT = (By.ID, "otp")
    VERIFY_OTP = (By.ID, "verifyOTP")
    OTP_ERROR = (By.CSS_SELECTOR, "div.alert-inpage.error")
    OTP_RESEND = (By.ID, "sendNewCode")

    # Holdings
    NAV_ACCOUNTS = (By.CSS_SELECTOR, "a.nav-accounts")
    NAV_HOLDINGS = (By.ID, "nav-holdings")
    SHOWING_SELECT = (By.CSS_SELECTOR, "mat-select[aria-label^='Showing']")
    PRIOR_CLOSE_OPTION = (By.XPATH, "//mat-option//span[normalize-space()='Prior Close']")
    DOWNLOAD_BTN = (By.CSS_SELECTOR, "button[aria-label='Download']")
    EXPORT_EXCEL = (By.CSS_SELECTOR, "button[aria-label='Export to Excel']")
    HOLDINGS_ROWS = (By.CSS_SELECTOR, "table tbody tr, .mat-row, .mat-mdc-row")
    LOADING_SPINNER = (By.CSS_SELECTOR, "mat-progress-spinner, mat-spinner, .mat-progress-spinner, .mat-spinner")

    # History
    NAV_HISTORY = (By.ID, "nav-history")
    TIME_PERIOD = (By.ID, "timeperiod")
    PREV_BUSINESS_DAY = (By.XPATH, "//mat-option//span[normalize-space()='Previous Business Day']")
    APPLY_FILTERS = (By.XPATH, "//button[.//span[normalize-space()='Apply Filters']]")
    HISTORY_ROWS = (By.CSS_SELECTOR, "table tbody tr, .mat-row, .mat-mdc-row")

    # Logout
    USER_MENU = (By.CSS_SELECTOR, "button[aria-label='Settings and Logout']")
    LOGOUT_BTN = (By.XPATH, "//button[.//span[normalize-space()='Logout']]")
