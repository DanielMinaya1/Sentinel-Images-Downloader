import rasterio
from sentinel_images_downloader.downloader.base_downloader import SentinelDownloader
from sentinel_images_downloader.utils.io_utils import load_json
from pathlib import Path 
import logging

logger = logging.getLogger(__name__)

class Sentinel2(SentinelDownloader):
    def __init__(self, username, password, tile_ids, product_level, relative_orbits_path, 
        initial_date, last_date, band_selection, output_dir):
        """
        Args:
            tile_ids (list[str]): Ids of the tiles to download.
            product_level (str): Level of the product (can be "L1C" or "L2A").
            relative_orbits_path (str): Path to JSON containing orbit for each tile.
            band_selection (list[str]): Bands to download.
        """
        super().__init__(username, password, initial_date, last_date, output_dir)
        self.data_collection = 'SENTINEL-2'

        self.tile_ids = tile_ids
        self.product_level = product_level
        self.band_selection = band_selection

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
            f"product_level={self.product_level}",
            f"range_date={self.initial_date} to {self.last_date}",
            f"output_dir={self.output_dir}"
        ]
        description = ", ".join(attributes)
        return f"Sentinel-2({description})"

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
            f"{self.data_url}/Products?$filter=Collection/Name eq '{self.data_collection}'",
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
        logger.info(self)
        for tile_id in self.tile_ids:
            self.download_tile(tile_id)

    def validate_download(self, file_path):
        """
        Validates the downloaded file.

        Raises:
            Exception: If the file is corrupt or unreadable.
        """
        if file_path.suffix.lower() != ".jp2":
            return
        try:
            with rasterio.open(file_path) as src:
                src.meta

        except Exception as e:
            message = f"Invalid JP2 file: {e}"
            logger.error(message, exc_info=True)
            raise ValueError(message)