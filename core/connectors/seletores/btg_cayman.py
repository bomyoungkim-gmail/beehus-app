from dataclasses import dataclass
from selenium.webdriver.common.by import By


@dataclass(frozen=True)
class SeletorBtgCayman:
    """Selectors for the BTG Cayman portal."""

    URL_BASE = "https://app.btgpactual.com/login"

    # Login
    EMAIL = (By.CSS_SELECTOR, "input#email")
    PASSWORD = (By.CSS_SELECTOR, "input#password")
    SIGN_IN = (By.XPATH, "//button[normalize-space()='Sign in']")
    PORTAL_GLOBAL = (By.CSS_SELECTOR, "fieldset.login__external-link")
    PORTAL_GLOBAL_ALT = (By.XPATH, "//p[normalize-space()='Portal Global']")
    PORTAL_GLOBAL_CARD = (
        By.XPATH,
        "//a[.//span[normalize-space()='Portal Global'] or .//p[normalize-space()='Portal Global'] or .//*[normalize-space()='Portal Global']]",
    )

    # OTP
    OTP_CODE = (By.ID, "code")
    OTP_CONTINUE = (By.XPATH, "//button[normalize-space()='Continue']")

    # Country selection
    COUNTRY_CAYMAN = (By.XPATH, "//div[contains(@class,'orq-tabs__tab')]//span[normalize-space()='Cayman Islands']")

    # Accounts
    CHECKBOX_TOTAL = (By.CSS_SELECTOR, "orq-checkbox#Checkbox_TotalAccount input")
    ACCOUNT_CHECKBOXES = (By.CSS_SELECTOR, "input[type='checkbox'][aria-label='Checkbox']")
    ACCESS_BTN = (By.XPATH, "//button[normalize-space()='Access']")

    # Modal
    DONT_SHOW_AGAIN = (By.XPATH, "//span[normalize-space()=\"Don't show again\"]")
    MODAL_OVERLAY = (By.CSS_SELECTOR, "div.orq-modal__overlay")
    MODAL_CLOSE_BUTTON = (By.CSS_SELECTOR, "button.orq-modal__close-button")
    MODAL_CLOSE = (By.CSS_SELECTOR, "button[aria-label='Close'], button.close, .icon-close")
    MODAL_SKIP = (By.XPATH, "//button[contains(normalize-space(), 'Skip') or contains(normalize-space(), 'Close')]")
    GENERIC_OVERLAY = (
        By.CSS_SELECTOR,
        "div.overlay.ng-star-inserted, div.overlay, .cdk-overlay-backdrop, .cdk-overlay-backdrop-showing",
    )

    # Filters / export
    DATE_INPUT = (By.CSS_SELECTOR, "input[placeholder*='Data de']")
    CHECK_ALL_ANCHOR_SUMMARY = (
        By.XPATH,
        "//div[contains(@class,'card-btg')][.//h3[contains(normalize-space(),'Summary of holdings')]]//a[contains(@class,'see-more') and contains(normalize-space(),'Check all')]",
    )
    CHECK_ALL_ANCHOR = (
        By.XPATH,
        "//div[contains(@class,'card-btg') and not(ancestor::app-history)]//a[contains(@class,'see-more') and contains(normalize-space(),'Check all')]",
    )
    EXPORT_OPTIONS_BTN = (
        By.XPATH,
        "//button[contains(normalize-space(.), 'Export options') or .//span[contains(normalize-space(.), 'Export options')] or ancestor::div[contains(@class,'expand-btn')]]",
    )
    EXPORT_ALL_OPTION = (
        By.XPATH,
        "//div[contains(@class,'item') and contains(normalize-space(.), 'Export all')] | //*[self::button or self::div or self::span][contains(normalize-space(.), 'Export all')]",
    )

    SIDEBAR_TOGGLE = (By.CSS_SELECTOR, "button.burguer-menu-button")
    SIDEBAR_PORTFOLIO = (By.XPATH, "//button[.//p[normalize-space()='Portfolio']]")
    PORTFOLIO_CHECK_ALL_ACTIVITIES = (
        By.XPATH,
        "//app-title-home[.//h1[contains(normalize-space(),'Activities history')]]//a[contains(@class,'orq-link') and .//span[contains(@class,'orq-link__label') and normalize-space()='Check all']]",
    )
    PORTFOLIO_CHECK_ALL = (
        By.XPATH,
        "//app-history//a[(.//span[normalize-space()='Check all'] or contains(normalize-space(),'Check all')) and (contains(@class,'orq-link') or contains(@class,'see-more'))]",
    )

    FILTERS_BTN = (By.XPATH, "//button[normalize-space()='Filters']")
    TIME_PERIOD = (By.XPATH, "//label[.//span[normalize-space()='Time Period']]")
    CUSTOM_PERIOD = (By.XPATH, "//div[contains(@class,'description') and normalize-space()='Custom period']")
    CUSTOM_DATE_INPUTS = (By.CSS_SELECTOR, "input[placeholder*='Click and select']")
    FILTER_BTN = (By.XPATH, "//button[normalize-space()='Filter']")
    EXPORT_BTN = (By.XPATH, "//button[normalize-space()='Export']")
    DOWNLOAD_BTN = (By.XPATH, "//button[normalize-space()='Download']")
    EXPORT_ALL_HISTORY_BTN = (
        By.XPATH,
        "//button[normalize-space()='Export all' or .//span[normalize-space()='Export all']]",
    )

    # Logout
    PROFILE_MENU = (By.ID, "menuProfile")
    SIGN_OUT = (By.XPATH, "//div[contains(@class,'header__menu--signout')]//p[normalize-space()='Sign Out']")

