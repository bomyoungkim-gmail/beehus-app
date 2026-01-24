"""
Date calculation utilities for connectors.
Handles business day calculations and date formatting for export operations.
"""

from datetime import datetime
from typing import Optional
from core.utils.date_utils import get_previous_business_day, get_today


def calculate_export_date(
    date_mode: str,
    lag_days: int,
    specific_date: Optional[str],
    region: str = "BR",
    state: str = "SP",
    output_format: str = "%d/%m/%Y"
) -> str:
    """
    Calculate export date based on job parameters.
    
    Args:
        date_mode: "lag" or "specific"
        lag_days: Number of business days to go back (e.g., 1 for D-1)
        specific_date: Specific date in YYYY-MM-DD format
        region: Region for business day calculation
        state: State for business day calculation
        output_format: Output date format
        
    Returns:
        Formatted date string
    """
    if date_mode == "specific" and specific_date:
        # Parse specific date and format
        try:
            date_obj = datetime.strptime(specific_date, "%Y-%m-%d")
            return date_obj.strftime(output_format)
        except ValueError:
            # Fallback to lag mode if parsing fails
            pass
    
    # Lag mode (default)
    previous_day = get_previous_business_day(
        ref_date=get_today(),
        region=region,
        state=state,
        days=lag_days
    )
    return previous_day.strftime(output_format)


def calculate_holdings_date(params: dict, output_format: str = "%d/%m/%Y") -> str:
    """
    Calculate holdings export date from job parameters.
    
    Args:
        params: Job parameters dictionary
        output_format: Output date format
        
    Returns:
        Formatted holdings date
    """
    return calculate_export_date(
        date_mode=params.get("date_mode", "lag"),
        lag_days=params.get("holdings_lag_days", 1),
        specific_date=params.get("holdings_date"),
        output_format=output_format
    )


def calculate_history_date(params: dict, output_format: str = "%d/%m/%Y") -> str:
    """
    Calculate history export date from job parameters.
    
    Args:
        params: Job parameters dictionary
        output_format: Output date format
        
    Returns:
        Formatted history date
    """
    return calculate_export_date(
        date_mode=params.get("date_mode", "lag"),
        lag_days=params.get("history_lag_days", 2),
        specific_date=params.get("history_date"),
        output_format=output_format
    )
