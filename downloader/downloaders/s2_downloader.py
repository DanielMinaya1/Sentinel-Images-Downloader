import logging
from pathlib import Path

import rasterio

from downloader.config.templates import S2_QUERY, S2_QUERY_NO_ORBIT
from downloader.downloaders.base_downloader import SentinelDownloader
from downloader.models import (
    RunSummary,
    Sentinel2DownloadStatus,
    Sentinel2Response,
    SentinelProduct,
)
from downloader.storage.repositories import OrbitRepository

logger = logging.getLogger(__name__)


class Sentinel2(SentinelDownloader):
    response_class = Sentinel2Response

    def __init__(
        self,
        username: str,
        password: str,
        tile_ids: list[str],
        product_level: str,
        db_path: str | Path,
        initial_date: str,
        last_date: str,
        band_selection: list[str],
        output_dir: str,
        max_retries: int,
    ):
        """
        Args:
            tile_ids (list[str]): Ids of the tiles to download.
            product_level (str): Level of the product
                                 (can be "L1C" or "L2A").
            db_path (str): Path to the SQLite database containing the
                           `s2_orbits` table (tile_id -> relative orbit).
            band_selection (list[str]): Bands to download.
        """
        super().__init__(
            username=username,
            password=password,
            initial_date=initial_date,
            last_date=last_date,
            output_dir=output_dir,
            max_retries=max_retries,
        )
        self.data_collection = "SENTINEL-2"

        self.tile_ids = tile_ids
        self.product_level = product_level
        self.band_selection = band_selection

        self.orbit_repository = OrbitRepository(db_path)
        self.orbits = self.orbit_repository.all()

    def __repr__(self) -> str:
        """
        Returns a string representation of the Sentinel-2 object,
        summarizing its key attributes.

        Includes:
        - Tile IDs with their corresponding orbits
        - Selected bands
        - Product level
        - Date range (initial to last date)
        - Output directory

        Example:
            Sentinel-2(
                tile_ids=[
                    ('T19HCC', 'R096'),
                    ('T19KCP', 'R139')
                ],
                bands=['B02', 'B03'],
                product_level='L2A',
                range_date='2023-01-01 to 2023-12-31',
                output_dir='/data/sentinel2/'
            )
        """
        attributes = [
            f"tile_ids={[(t, self.orbits.get(t)) for t in self.tile_ids]}",
            f"bands={self.band_selection}",
            f"product_level={self.product_level}",
            f"range_date={self.initial_date} to {self.last_date}",
            f"output_dir={self.output_dir}",
        ]
        description = ", ".join(attributes)
        return f"Sentinel-2({description})"

    def get_query(
        self,
        tile_id: str,
        initial_date: str,
        last_date: str,
    ) -> str:
        """
        Constructs an OData query for retrieving Sentinel-2
        products from the Copernicus Data Space API.

        Args:
            tile_id (str): The Sentinel-2 tile ID to filter results.
            initial_date (str): The start date for the query in the
                                format 'YYYY-MM-DD'.
            last_date (str): The end date for the query in the format
                             'YYYY-MM-DD'.

        Returns:
            str: A formatted OData query string.
        """
        if tile_id in self.orbits:
            return S2_QUERY.format(
                data_url=self.data_url,
                data_collection=self.data_collection,
                initial_date=initial_date,
                last_date=last_date,
                tile_id=tile_id,
                product_level=self.product_level,
                orbit_number=self.orbits[tile_id],
            )
        else:
            return S2_QUERY_NO_ORBIT.format(
                data_url=self.data_url,
                data_collection=self.data_collection,
                initial_date=initial_date,
                last_date=last_date,
                tile_id=tile_id,
                product_level=self.product_level,
            )

    def filter_images(self, files_list: list[str]) -> list[str]:
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
        return [
            file for file in img_data_files if any(band in file for band in self.band_selection)
        ]

    def download(self) -> RunSummary:
        """
        Initiates the download process for all specified Sentinel-2 tiles.

        This method:
        1. Prints a summary of the current download configuration
           (`self.__repr__()`).
        2. Iterates over all tile IDs stored in `self.tile_ids`.
        3. Calls `self.download_tile(tile_id)` to handle the download
           process for each tile.

        Returns:
            RunSummary: The outcome of downloading every tile, for use by
            callers that want to report on or inspect what happened.

        Notes:
            - The `self.download_tile()` method is responsible for querying
              and downloading products.
            - This function acts as the main entry point for triggering the
              download process.
        """
        logger.info(self)
        run_summary = RunSummary()
        for tile_id in self.tile_ids:
            run_summary.tiles.append(self.download_tile(tile_id))
        return run_summary

    def validate_download(self, file_path: Path) -> None:
        """
        Validates the downloaded file.

        Raises:
            Exception: If the file is corrupt or unreadable.
        """
        if file_path.suffix.lower() != ".jp2":
            return
        try:
            with rasterio.open(file_path) as src:
                _ = src.meta

        except Exception as e:
            message = f"Invalid JP2 file: {e}"
            logger.error(message, exc_info=True)
            raise ValueError(message) from e

    def _create_status(
        self,
        product: SentinelProduct,
    ) -> Sentinel2DownloadStatus:
        return Sentinel2DownloadStatus(
            product_id=product.id,
            product_name=product.name,
            product_level=self.product_level,
            band_selection=self.band_selection,
        )
