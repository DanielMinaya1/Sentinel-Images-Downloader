from sentinel_images_downloader.config.endpoints import LOGIN_URL
import requests
import logging

logger = logging.getLogger(__name__)

def get_keycloak(username, password, client_id="cdse-public"):
    """
    Obtains an access token from Keycloak for authentication.

    Args:
        username (str): The username for authentication.
        password (str): The password associated with the username.
        client_id (str): The Keycloak client ID.

    Returns:
        str: The access token received from Keycloak.

    Raises:
        Exception: If the request to Keycloak fails or 
                   an access token is not found.
    """
    data = {
        "client_id": client_id,
        "username": username,
        "password": password,
        "grant_type": "password",
    }

    try:
        logger.info("Sending request to Keycloak...")
        response = requests.post(
            LOGIN_URL,
            data=data,
            allow_redirects=True,
        )
        response.raise_for_status()

        token = response.json().get("access_token")
        if not token:
            raise Exception("Access token not found in the response.")

        logger.info("Access token retrieved successfully.")
        return token

    except requests.exceptions.HTTPError as http_err:
        message = f"HTTP error occurred: {http_err} - {response.text}"
        logger.error(message)
        raise Exception(message) from http_err
    
    except requests.exceptions.RequestException as req_err:
        message = f"Request error occurred: {req_err}"
        logger.error(message)
        raise Exception(message) from req_err
    
    except Exception as e:
        message = f"Keycloak token creation failed. Response: {response.text}"
        logger.error(message)
        raise Exception(message) from e