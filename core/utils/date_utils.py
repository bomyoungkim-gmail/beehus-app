from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import holidays
from core.config import settings

def get_now() -> datetime:
    """
    Returns the current datetime in the configured timezone.
    """
    return datetime.now(ZoneInfo(settings.TIMEZONE))

def get_today() -> date:
    """
    Returns the current date in the configured timezone.
    """
    return get_now().date()

def get_previous_business_day(ref_date: date = None, region: str = "BR", state: str = "SP", days: int = 1) -> date:
    """
    Returns the previous business day (D-N) relative to ref_date,
    skipping weekends and holidays for the specified region.
    
    Args:
        ref_date: The reference date (defaults to today).
        region: Country code ('BR', 'US', 'CH', 'KY').
        state: State code (e.g., 'SP' for Brazil, 'NY' for US, 'ZH' for Zurich).
        days: Number of business days to go back (default 1).
    """
    if ref_date is None:
        ref_date = get_today()
    
    # Select holiday calendar
    if region == "BR":
        # Create a custom holiday object possibly including subdivision
        country_holidays = holidays.Brazil(subdiv=state)
    elif region == "US":
        country_holidays = holidays.US(subdiv=state if state else 'NY')
    elif region == "CH":
        # Zurich defaults
        country_holidays = holidays.Switzerland(subdiv=state if state else 'ZH')
    elif region == "KY":
        # Cayman Islands
        country_holidays = holidays.CaymanIslands()
    else:
        # Fallback to empty (only weekends) or Brazil default?
        country_holidays = holidays.Brazil()

    candidate = ref_date
    
    # Go back N business days
    for _ in range(days):
        candidate -= timedelta(days=1)
        while True:
            # Check standard weekend (Saturday=5, Sunday=6)
            if candidate.weekday() >= 5:
                candidate -= timedelta(days=1)
                continue
            
            # Check holiday
            if candidate in country_holidays:
                candidate -= timedelta(days=1)
                continue
                
            # If neither weekend nor holiday -> found a business day step
            break
        
    return candidate
