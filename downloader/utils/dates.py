from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def process_dates(initial_date, last_date):
    """
    Generates a list of monthly time ranges between two dates.

    Args:
        initial_date (str): The start date in 'YYYY-MM-DD' format.
        last_date (str): The end date in 'YYYY-MM-DD' format.

    Returns:
        list of tuples: Monthly ISO 8601 time ranges.

    Example:
        >>> process_dates("2023-01-15", "2023-03-10")
        [
            ('2023-01-15T00:00:00.000Z', '2023-01-31T23:59:59.999Z'),
            ('2023-02-01T00:00:00.000Z', '2023-02-28T23:59:59.999Z'),
            ('2023-03-01T00:00:00.000Z', '2023-03-10T23:59:59.999Z')
        ]
    """
    try:
        start = datetime.strptime(initial_date, "%Y-%m-%d")
        end = datetime.strptime(last_date, "%Y-%m-%d")

    except ValueError as e:
        message = (
            f"Invalid date format. "
            f"initial_date='{initial_date}', "
            f"last_date='{last_date}'"
        )
        logger.error(message, exc_info=True)
        raise ValueError("Dates must be in 'YYYY-MM-DD' format.") from e

    if start > end:
        message = (
            f"Dates were passed in the wrong order: "
            f"start={start.date()}, end={end.date()}. "
            f"Swapping them."
        )
        logger.warning(message)
        start, end = end, start

    monthly_ranges = []
    current_start = start

    while current_start <= end:
        next_month_start = (
            current_start.replace(day=28) + timedelta(days=4)
        ).replace(day=1)
        current_end = min(next_month_start - timedelta(seconds=1), end)

        monthly_ranges.append((
            current_start.strftime('%Y-%m-%dT00:00:00.000Z'),
            current_end.strftime('%Y-%m-%dT23:59:59.999Z'),
        ))

        current_start = current_end + timedelta(seconds=1)
    return monthly_ranges
