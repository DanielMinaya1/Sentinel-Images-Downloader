from collections import defaultdict
import json
import logging

logger = logging.getLogger(__name__)

def load_json(file_path, default_type=None):
    """
    Loads a JSON file and returns its contents as a dictionary. 
    
    If the file does not exist, returns an empty dictionary or a `defaultdict` 
    if `default_type` is provided.

    Args:
        file_path (Path): The path to the JSON file.
        default_type (Callable[[], Any], optional): A callable that provides
            the default value type for a `defaultdict`. If None, a standard 
            dictionary is returned.

    Returns:
        dict or defaultdict: The parsed JSON content as a dictionary, or a 
        defaultdict if `default_type` is specified.
    """
    if file_path.is_file():
        logger.info(f"Reading {file_path}...")
        try:
            with file_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
                return defaultdict(default_type, data) if default_type else data
            
        except json.JSONDecodeError as e:
            logger.error(f"Malformed JSON in {file_path}: {e}")
            raise
    
    else:
        logger.warning(f"JSON file not found at {file_path}. Returning empty.") 
        return defaultdict(default_type) if default_type else {}

def download_file(response, file_path, chunk_size=8192):
    """
    Downloads a file from an HTTP response and saves it locally.

    Args:
        response (requests.Response): The HTTP response object containing the file content.
        file_path (str): The path where the file should be saved.
        chunk_size (int, optional): The chunk size for writing. Default is 8192 bytes.
    """
    try:
        with file_path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    file.write(chunk)
        logger.info(f"{file_path} downloaded successfully.")

    except Exception as e:
        logger.error(f"Failed to write file to {file_path}: {e}", exc_info=True)
        raise

    finally:
        response.close()