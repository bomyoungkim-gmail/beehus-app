from dataclasses import dataclass
from selenium.webdriver.common.by import By


@dataclass(frozen=True)
class SeletorMorganStanley:
    """Selectors for the Morgan Stanley portal."""

    URL_BASE = "https://login.morganstanleyclientserv.com/ux/"
    URL_HOLDINGS_REFER = (
        "https://login.morganstanleyclientserv.com/ux/"
        "#/accounts/holdings?refer=mso-menu"
    )
    URL_CANDIDATES = (
        URL_BASE,
        URL_HOLDINGS_REFER,
    )

    # Login
    USERNAME_INPUT = (
        By.CSS_SELECTOR,
        "input[formcontrolname='Username'], input[autocomplete='username']",
    )
    PASSWORD_INPUT = (
        By.CSS_SELECTOR,
        "input[type='password'][aria-label='Password'], input[type='password'][autocomplete='current-password']",
    )
    LOGIN_BUTTON = (
        By.CSS_SELECTOR,
        "button#btnLogin, button[type='submit'][data-form-type*='login']",
    )
    LOGIN_ERROR_MESSAGE = (
        By.CSS_SELECTOR,
        ".ms-form__input-error-msg, .ms-form__error, [track-id*='error'], [role='alert'], .mat-mdc-snack-bar-label",
    )
    LOGIN_ERROR_BANNER = (
        By.XPATH,
        "//*[contains(@class,'alert') or contains(@class,'error') or @role='alert' or @aria-live='assertive']",
    )

    # Post-login verification / MFA interstitial
    VERIFY_IDENTITY_TITLE = (
        By.XPATH,
        "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'verify identity') or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'verify your identity')]",
    )
    VERIFY_CONTINUE_BUTTON = (
        By.XPATH,
        "//button[normalize-space()='Continue' or .//span[normalize-space()='Continue']]",
    )
    MFA_CODE_INPUT = (
        By.CSS_SELECTOR,
        "input[autocomplete='one-time-code'], input[name*='code' i], input[id*='otp' i], input[id*='code' i]",
    )
    MFA_SUBMIT_BUTTON = (
        By.XPATH,
        "//button[normalize-space()='Verify' or normalize-space()='Submit' or normalize-space()='Continue']",
    )
    MFA_DELIVER_ROUTE_MARKER = (
        By.XPATH,
        "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'verification code') or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'one-time code')]",
    )
    MFA_SEND_OTP_COMPONENT = (
        By.CSS_SELECTOR,
        "auth-mfa-prompt, auth-otp, auth-send-otp",
    )
    SERVICE_UNAVAILABLE_TITLE = (
        By.XPATH,
        "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'this service is temporarily unavailable')]",
    )
    SERVICE_UNAVAILABLE_CLOSE = (
        By.XPATH,
        "//button[@aria-label='close' or contains(@class,'ms-theme-icon-close')]",
    )
    SERVICE_UNAVAILABLE_BANNER = (
        By.XPATH,
        "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'this service is currently unavailable') or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'this service is temporarily unavailable')]",
    )
    SERVICE_UNAVAILABLE_INTERNAL_ERROR = (
        By.XPATH,
        "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'internal error submitting your change') or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'please try making your changes again later')]",
    )
    SERVICE_UNAVAILABLE_HELP_PHONE = (
        By.XPATH,
        "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'client service center')]",
    )
    PASSWORD_RESET_OR_LOCK_NOTICE = (
        By.XPATH,
        "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'locked') or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'reset your password') or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invalid username') or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'invalid password')]",
    )

    # Navigation
    ACCOUNTS_MENU = (
        By.XPATH,
        "//a[contains(@class,'ms-menu-item__link-anchor') and .//span[normalize-space()='Accounts']]",
    )
    HOLDINGS_SUBMENU = (
        By.XPATH,
        "//a[contains(@class,'ms-menu-item__link_submenu') and .//span[normalize-space()='Holdings']]",
    )
    ACTIVITY_SUBMENU = (
        By.XPATH,
        "//a[contains(@class,'ms-menu-item__link_submenu') and .//span[normalize-space()='Activity']]",
    )

    # Download
    DOWNLOAD_ACTION = (
        By.XPATH,
        "//li[@track-id='msoAccounts.download' or (.//span[normalize-space()='Download'] and contains(@class,'ms-accounts-rail-actions__item'))]",
    )

    # Activity custom date range
    PERIOD_TRIGGER = (
        By.CSS_SELECTOR,
        "[track-id='select.labelContainer'][role='button'], [track-id='select.popover'] [role='button']",
    )
    CUSTOM_DATE_RANGE_OPTION = (
        By.XPATH,
        "//*[@track-id='select.optionText' and normalize-space()='Custom Date Range']",
    )
    CUSTOM_DATE_RANGE_MODAL_TITLE = (
        By.XPATH,
        "//h1[normalize-space()='Custom Date Range']",
    )
    FROM_DATE_INPUT = (By.CSS_SELECTOR, "input#ms-form-datepicker-input-0")
    TO_DATE_INPUT = (By.CSS_SELECTOR, "input#ms-form-datepicker-input-1")
    APPLY_DATE_RANGE_BUTTON = (By.CSS_SELECTOR, "button[track-id='activity.selectDateRange']")
    CALENDAR = (By.CSS_SELECTOR, "mat-calendar")
    CALENDAR_MONTH_SELECT = (By.CSS_SELECTOR, "mat-calendar select[id^='ms-select-month-']")
    CALENDAR_YEAR_SELECT = (By.CSS_SELECTOR, "mat-calendar select[id^='ms-select-year-']")

    # Logout
    LOGOUT_BUTTON = (
        By.XPATH,
        "//a[contains(@class,'ms-atrium-logout') and normalize-space()='Log out']",
    )
