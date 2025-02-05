from downloader.utils import load_json, process_dates, get_keycloak, download_file
from downloader.xml_utils import parse_manifest, get_files
from pathlib import Path
from tqdm import tqdm
import requests
import time

data_url = "https://catalogue.dataspace.copernicus.eu/odata/v1"
download_url = "https://download.dataspace.copernicus.eu/odata/v1"

class Sentinel2:
    def __init__(self, username, password, tile_ids, product_level, relative_orbits_path, 
        initial_date, last_date, band_selection, output_dir):
        """
        Args:
            tile_ids (list[str]): Ids of the tiles to download.
            product_level (str): Level of the product (can be "L1C" or "L2A").
            relative_orbits_path (str): Path to JSON containing orbit for each tile.
            initial_date (str): Start date to download, in format YYYY-MM-DD.
            last_date (str): End date to download, in format YYYY-MM-DD.
            band_selection (list[str]): Bands to download.
            output_dir (str): Path to save the files
        """
        self.data_collection = 'SENTINEL-2'
        self.username = username
        self.password = password

        self.tile_ids = tile_ids
        self.product_level = product_level
        self.band_selection = band_selection

        self.initial_date = initial_date
        self.last_date = last_date
        self.date_ranges = process_dates(initial_date, last_date)

        self.output_dir = Path(output_dir)
        self.relative_orbits_path = Path(relative_orbits_path)
        self.orbits = load_json(self.relative_orbits_path)

    def __repr__(self):
        """
        Returns a string representation of the Sentinel-2 object, summarizing its key attributes.

        Includes:
        - Tile IDs with their corresponding orbits
        - Selected bands
        - Product level
        - Date range (initial to last date)
        - Output directory

        Example:
            Sentinel-2(tile_ids=[('T19HCC', 'R096'), ('T19KCP', 'R139')], bands=['B02', 'B03'], 
                       level='L2A', range_date='2023-01-01 to 2023-12-31', 
                       output_dir='/data/sentinel2/')
        """
        attributes = [
            f"tile_ids={[(tile_id, self.orbits[tile_id]) for tile_id in self.tile_ids]}",
            f"bands={self.band_selection}",
            f"level={self.product_level}",
            f"range_date={self.initial_date} to {self.last_date}",
            f"output_dir={self.output_dir}"
        ]
        description = ", ".join(attributes)
        return f"Sentinel-2({description})"

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
        return product_path

    def get_query(self, tile_id, initial_date, last_date):
        """
        Constructs an OData query for retrieving Sentinel-2 products from the Copernicus Data Space API.

        Args:
            tile_id (str): The Sentinel-2 tile ID to filter results.
            initial_date (str): The start date for the query in the format 'YYYY-MM-DD'.
            last_date (str): The end date for the query in the format 'YYYY-MM-DD'.

        Returns:
            str: A formatted OData query string.
        """
        query = [
            f"{data_url}/Products?$filter=Collection/Name eq '{self.data_collection}'",
            f"ContentDate/Start ge {initial_date}",
            f"ContentDate/End le {last_date}",
            f"contains(Name, '{tile_id}')",
            f"contains(Name, '{self.product_level}')",
            f"contains(Name, '{self.orbits[tile_id]}')",
            "Online eq True&$top=500&$orderby=ContentDate/Start asc",
        ]
        return " and ".join(query)

    def filter_images(self, files_list):
        """
        Filters image files based on specific criteria.

        This method retains only files located in the "IMG_DATA" directory 
        and further filters them to include only those containing one of 
        the specified bands.

        Args:
            files_list (list of str): List of file paths to be filtered.

        Returns:
            list of str: A filtered list of file paths that match the criteria.
        """
        img_data_files = [file for file in files_list if "IMG_DATA" in file]
        return [file for file in img_data_files if any(band in file for band in self.band_selection)]

    def download_product(self, session, SAFE_product):
        """
        Downloads a Sentinel-2 product and its relevant files.

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
        product_base_url = f"{download_url}/Products({product_id})/Nodes({product_name})"

        product_path = self.prepare_output(product_name)

        manifest_path = product_path / "manifest.safe"
        if not manifest_path.is_file():
            manifest_url = f"{product_base_url}/Nodes(manifest.safe)/$value"
            response = session.get(manifest_url, allow_redirects=False)
            download_file(response, manifest_path)

        xmldict = parse_manifest(manifest_path)
        files_list = self.filter_images(get_files(xmldict))

        for file in files_list:
            file_path = product_path / file
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if file_path.is_file():
                continue

            nodes_str = "/".join([f"Nodes({node})" for node in file.split("/")])
            file_url = f"{product_base_url}/{nodes_str}/$value"
            response = session.get(file_url, allow_redirects=False)
            download_file(response, file_path)

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
            query = self.get_query(tile_id, initial_date, last_date)
            response = requests.get(query)
            data = response.json()

            desc = f"Downloading tile {tile_id} from {initial_date[:10]} to {last_date[:10]}"
            for SAFE_product in tqdm(data.get("value", []), desc=desc):
                print()
                with self.init_session() as session:
                    self.download_product(session, SAFE_product)
            time.sleep(10)

    def download(self):
        """
        Initiates the download process for all specified Sentinel-2 tiles.

        This method:
        1. Prints a summary of the current download configuration (`self.__repr__()`).
        2. Iterates over all tile IDs stored in `self.tile_ids`.
        3. Calls `self.download_tile(tile_id)` to handle the download process for each tile.

        Notes:
            - The `self.download_tile()` method is responsible for querying and downloading products.
            - This function acts as the main entry point for triggering the download process.
        """
        print(self)
        for tile_id in self.tile_ids:
            self.download_tile(tile_id)