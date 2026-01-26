from selenium.webdriver.common.by import By


class SeletorJPMorgan:
    URL_BASE = "https://secure.chase.com/web/auth/?treatment=jpo#/logon/logon/chaseOnline"

    HOME_SIGNIN_BTN = (By.CSS_SELECTOR, "a.signInBtn")

    # Login
    LOGIN_USERNAME = (By.ID, "userId-input-field-input")
    LOGIN_PASSWORD = (By.ID, "password-input-field-input")
    LOGIN_SUBMIT = (By.ID, "signin-button")
    LOGIN_SUBMIT_FALLBACK = (By.CSS_SELECTOR, "button[type='submit']")

    # MFA
    MFA_DROPDOWN = (By.ID, "simplerAuth-dropdownoptions-styledselect")
    MFA_OPTION_SMS = (By.ID, "container-1-simplerAuth-dropdownoptions-styledselect")
    MFA_OPTION_DEFAULT = (By.ID, "container-3-simplerAuth-dropdownoptions-styledselect")
    MFA_NEXT = (By.ID, "requestIdentificationCode-sm")
    MFA_NEXT_FALLBACK = (By.ID, "requestIdentificationCode")
    MFA_OTP_INPUT = (By.ID, "otpcode_input-input-field")
    MFA_PASSWORD_INPUT = (By.ID, "password_input-input-field")
    MFA_NEXT_AFTER_OTP = (By.ID, "log_on_to_landing_page-sm")

    # Navigation
    MENU_INVESTMENTS = (By.ID, "requestChaseInvestmentsMenu")
    MENU_POSITIONS = (By.CSS_SELECTOR, "[data-testid='requestInvestmentPositionSummary']")

    # Positions filters
    ACCOUNTS_DROPDOWN = (By.ID, "select-accounts-selector")
    ACCOUNTS_ALL_ELIGIBLE = (By.XPATH, "//span[normalize-space()='All Eligible Accounts']")
    SHOW_ALL_TAX_LOTS = (By.ID, "input-view-taxlots-switch")

    # Export flow
    THINGS_YOU_CAN_DO = (By.ID, "header-things-you-can-do")
    EXPORT_AS_GROUP = (By.ID, "title-2-things-you-can-do")
    EXPORT_AS_EXCEL = (By.ID, "item-0-requestExportAsMicrosoftExcel")
    TRANSACTIONS_TAB = (By.ID, "transactions")
    CUSTOM_RANGE = (By.XPATH, "//div[contains(@class,'radio-button__primary-label') and normalize-space()='Custom']")
    CUSTOM_FROM = (By.ID, "custom-from-date-input-input")
    CUSTOM_TO = (By.ID, "custom-to-date-input-input")
    CUSTOM_APPLY = (By.CSS_SELECTOR, "button[data-testid='custom-date-range-apply']")
    EXPORT_BUTTON = (By.CSS_SELECTOR, "button[aria-labelledby='export-button-label']")
    EXPORT_MENU_EXCEL = (By.CSS_SELECTOR, "button.menu-button-item__item[data-label='Microsoft Excel']")

    # Logout
    SIGN_OUT = (By.ID, "brand_bar_sign_in_out")
