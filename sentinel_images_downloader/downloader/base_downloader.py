from sentinel_images_downloader.config.endpoints import DATA_URL, DOWNLOAD_URL
from sentinel_images_downloader.utils.io_utils import download_file
from sentinel_images_downloader.utils.auth import get_keycloak
from sentinel_images_downloader.utils.dates import process_dates
from sentinel_images_downloader.utils.xml_utils import parse_manifest, get_files
from abc import ABC, abstractmethod
from pathlib import Path
from tqdm import tqdm
import requests
import time 
import logging

logger = logging.getLogger(__name__)

class SentinelDownloader(ABC):
    def __init__(self, username, password, initial_date, last_date, output_dir, max_retries):
        """
        Args:
            username (str): Copernicus API username.
            password (str): Copernicus API password.
            initial_date (str): Start date to download, in format YYYY-MM-DD.
            last_date (str): End date to download, in format YYYY-MM-DD.
            output_dir (str): Path to save the files.
            max_retries (int): Number of retries if corrupt file.
        """
        self.username = username
        self.password = password

        self.data_url = DATA_URL
        self.download_url = DOWNLOAD_URL
    
        self.initial_date = initial_date
        self.last_date = last_date
        self.date_ranges = process_dates(initial_date, last_date)

        self.output_dir = Path(output_dir)

        self.max_retries = max_retries

    def init_session(self):
        """
        Initializes an authenticated session for accessing Copernicus Data Space API.

        This method:
        - Retrieves an access token using Keycloak authentication.
        - Creates a new `requests.Session` instance.
        - Updates the session headers to include the Bearer token for authorization.

        Returns:
            requests.Session: A configured session with authentication headers.
        """
        access_token = get_keycloak(self.username, self.password)
        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {access_token}"})
        return session

    def prepare_output(self, product_name):
        """
        Creates and returns the output directory for a given product.

        This method ensures that the directory exists before returning its path.

        Args:
            product_name (str): Name of the product for which the output directory is created.

        Returns:
            pathlib.Path: Path to the created (or existing) output directory.
        """
        product_path = self.output_dir / product_name
        product_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created output directory for the files: {product_path}")
        return product_path

    @abstractmethod
    def get_query(self, tile_id, initial_date, last_date):
        """Abstract method to be implemented by subclasses."""
        pass

    @abstractmethod
    def filter_images(self, files_list):
        """Abstract method to be implemented by subclasses."""
        pass

    def download_product(self, session, SAFE_product):
        """
        Downloads a Sentinel product and its relevant files.

        This method:
        1. Creates an output directory for the product.
        2. Downloads the `manifest.safe` file if it does not already exist.
        3. Parses the manifest file to retrieve the list of image files.
        4. Filters image files based on predefined criteria.
        5. Downloads the filtered image files if they do not already exist.

        Args:
            session (requests.Session): An authenticated session for making HTTP requests.
            SAFE_product (dict): A dictionary containing product metadata with:
                - "Id" (str): The product's unique identifier.
                - "Name" (str): The product's name.

        Notes:
            - The function ensures that files are downloaded only if they are missing.
            - The folder structure is preserved to match the Sentinel-2 SAFE format.
        """
        product_id = SAFE_product["Id"]
        product_name = SAFE_product["Name"]
        product_base_url = f"{self.download_url}/Products({product_id})/Nodes({product_name})"

        product_path = self.prepare_output(product_name)

        manifest_path = product_path / "manifest.safe"
        if not manifest_path.is_file():
            manifest_url = f"{product_base_url}/Nodes(manifest.safe)/$value"
            response = session.get(manifest_url, allow_redirects=False)
            download_file(response, manifest_path)

        xmldict = parse_manifest(manifest_path)
        files_list = self.filter_images(get_files(xmldict))
        logger.info(f"Found {len(files_list)} files to download")

        for file in files_list:
            file_path = product_path / file
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if file_path.is_file():
                logger.info(f"{file_path} already exists. Skipping...")
                continue

            nodes_str = "/".join([f"Nodes({node})" for node in file.split("/")])
            file_url = f"{product_base_url}/{nodes_str}/$value"

            for attempt in range(1, self.max_retries+1):
                try:
                    response = session.get(file_url, allow_redirects=False)
                    download_file(response, file_path)
                    self.validate_download(file_path)
                    break
                
                except Exception as e:
                    logger.warning(f"Attempt {attempt} failed for {file_path}: {e}")
                    file_path.unlink(missing_ok=True)

                    if attempt == self.max_retries:
                        logger.error(f"Max retries reached for {file_path}. Giving up.")
                        raise
                    else:
                        logger.info(f"Retrying download for {file_path}...")

    def download_tile(self, tile_id):
        """
        Downloads all Sentinel-2 products for a given tile across multiple date ranges.

        This method:
        1. Iterates through predefined date ranges.
        2. Constructs a query to fetch available Sentinel-2 products for the tile.
        3. Sends a request to retrieve product metadata.
        4. Iterates through each product, initializing a session and downloading the product files.
        5. Introduces a delay between requests to prevent excessive API calls.

        Args:
            tile_id (str): The Sentinel-2 tile ID to download data for.

        Notes:
            - Uses `self.get_query()` to construct the API request URL.
            - Uses `self.init_session()` to authenticate before downloading.
            - Uses `self.download_product()` to handle the actual file downloads.
            - Introduces a **10-second delay** (`time.sleep(10)`) between iterations to avoid rate limits.
        """
        for initial_date, last_date in self.date_ranges:
            logger.info(f"Downloading from {initial_date} to {last_date}")
            query = self.get_query(tile_id, initial_date, last_date)
            response = requests.get(query)
            data = response.json()
            
            desc = f"Downloading tile {tile_id} from {initial_date[:10]} to {last_date[:10]}"
            for SAFE_product in tqdm(data.get("value", []), desc=desc):
                print()            
                with self.init_session() as session:
                    self.download_product(session, SAFE_product)

            time.sleep(10)
    
    @abstractmethod
    def download(self):
        """Abstract method to be implemented by subclasses."""
        pass


    @abstractmethod
    def validate_download(self, file_path):
        """Abstract method to be implemented by subclasses."""
        pass