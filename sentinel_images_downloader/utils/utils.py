from collections import defaultdict
from datetime import datetime, timedelta
from tqdm import tqdm
import requests
import json
import logging

logger = logging.getLogger(__name__)

def get_keycloak(username, password):
    """
    Obtains an access token from Keycloak for authentication.

    Args:
        username (str): The username for authentication.
        password (str): The password associated with the username.

    Returns:
        str: The access token received from Keycloak.

    Raises:
        Exception: If the request to Keycloak fails or the response does not contain a valid access token.
    """
    data = {
        "client_id": "cdse-public",
        "username": username,
        "password": password,
        "grant_type": "password",
    }

    try:
        logger.info("Sending request to Keycloak...")
        response = requests.post(
            "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
            data=data,
            allow_redirects=True
        )
        response.raise_for_status()

        token = response.json().get("access_token")
        if not token:
            raise Exception("Access token not found in the response.")

        logger.info("Access token retrieved successfully.")

    except requests.exceptions.HTTPError as http_err:
        message = f"HTTP error occurred: {http_err} - {response.text}"
        logger.error(message)
        raise Exception(message)
    except requests.exceptions.RequestException as req_err:
        message = f"Request error occurred: {req_err}"
        logger.error(message)
        raise Exception(message)
    except Exception as e:
        message = f"Keycloak token creation failed. Response: {response.text}"
        logger.error(message)
        raise Exception(message)

    return token

def process_dates(initial_date, last_date):
    """
    Generates a list of monthly time ranges between two dates.

    Args:
        initial_date (str): The start date in the format 'YYYY-MM-DD'.
        last_date (str): The end date in the format 'YYYY-MM-DD'.

    Returns:
        list of tuples: Each tuple contains the start and end of a monthly time range 
                        formatted as ISO 8601 timestamps ('YYYY-MM-DDTHH:MM:SS.sssZ').

    Example:
        >>> process_dates("2023-01-15", "2023-03-10")
        [
            ('2023-01-15T00:00:00.000Z', '2023-01-31T23:59:59.999Z'),
            ('2023-02-01T00:00:00.000Z', '2023-02-28T23:59:59.999Z'),
            ('2023-03-01T00:00:00.000Z', '2023-03-10T23:59:59.999Z')
        ]
    """
    start = datetime.strptime(initial_date, "%Y-%m-%d")
    end = datetime.strptime(last_date, "%Y-%m-%d")

    monthly_ranges = []
    current_start = start

    while current_start <= end:
        next_month_start = (current_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        current_end = min(next_month_start - timedelta(seconds=1), end)

        monthly_ranges.append((
            f"{current_start.strftime('%Y-%m-%d')}T00:00:00.000Z",
            f"{current_end.strftime('%Y-%m-%d')}T23:59:59.999Z"
        ))
        current_start = current_end + timedelta(seconds=1)

    return monthly_ranges

def load_json(file_path, default_type=None):
    """
    Loads a JSON file and returns its contents as a dictionary. 
    
    If the file does not exist, returns an empty dictionary or a `defaultdict` 
    if `default_type` is provided.

    Args:
        file_path (Path): The path to the JSON file.
        default_type (Callable[[], Any], optional): A callable that provides the default 
            value type for a `defaultdict`. If None, a standard dictionary is returned.

    Returns:
        dict or defaultdict: The parsed JSON content as a dictionary, or a defaultdict 
        if `default_type` is specified.
    """
    if file_path.is_file():
        logger.info(f"Reading {file_path}...")
        with open(file_path, "r") as file:
            data = json.load(file)
            return defaultdict(default_type, data) if default_type else data
    return defaultdict(default_type) if default_type else {}

def download_file(response, file_path, chunk_size=8192):
    """
    Downloads a file from an HTTP response and saves it locally.

    Args:
        response (requests.Response): The HTTP response object containing the file content.
        file_path (str): The path of the file to save.
        chunk_size (int, optional): The size of chunks to read at a time. Default is 8192 bytes.
    """
    with open(file_path, "wb") as file:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                file.write(chunk)
    logger.info(f"{file_path} downloaded successfully.")
    response.close()