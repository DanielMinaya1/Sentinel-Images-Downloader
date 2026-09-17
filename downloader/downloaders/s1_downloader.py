import logging
from pathlib import Path

import rasterio

from downloader.config.templates import S1_QUERY
from downloader.downloaders.base_downloader import SentinelDownloader
from downloader.models import (
    RunSummary,
    Sentinel1DownloadStatus,
    Sentinel1Response,
    SentinelProduct,
)
from downloader.storage.repositories import FootprintRepository

logger = logging.getLogger(__name__)

class Sentinel1(SentinelDownloader):
    response_class = Sentinel1Response

    def __init__(
        self,
        username: str,
        password: str,
        db_path: str | Path,
        orbit_direction: str,
        product_type: str,
        polarization_mode: list[str],
        initial_date: str,
        last_date: str,
        output_dir: str,
        max_retries: int,
    ):
        """
        Args:
            db_path (str): Path to the SQLite database containing the
                           `s1_footprints` table of AOI footprints.
            orbit_direction (str): Orbit direction (can be
                                   "ASCENDING" or "DESCENDING").
            product_type (str): Sentinel-1 product type
                                (e.g., "GRDH", "SLC").
            polarization_mode (list[str]): Polarization modes
                                           (e.g., ["VV", "VH"]).
        """
        super().__init__(
            username=username,
            password=password,
            initial_date=initial_date,
            last_date=last_date,
            output_dir=output_dir,
            max_retries=max_retries,
        )
        self.data_collection = 'SENTINEL-1'

        self.orbit_direction = orbit_direction
        self.product_type = product_type
        self.polarization_mode = polarization_mode

        self.footprint_repository = FootprintRepository(db_path)
        self.footprints = self.footprint_repository.all()

    def __repr__(self) -> str:
        """
        Returns a string representation of the Sentinel-1 object, 
        summarizing its key attributes.

        Includes:
        - Footprint names
        - Polarization mode
        - Orbit diretion
        - Product type
        - Date range (initial to last date)
        - Output directory

        Example:
            Sentinel-1(
                footprints=['T19HCC', 'T19KCP'], 
                polarization_mode=['VV', 'VH'],
                product_type='GRD', 
                range_date='2023-01-01 to 2023-12-31', 
                output_dir='/data/sentinel1/'
            )
        """
        attributes = [
            f"footprints={list(self.footprints.keys())}",
            f"polarization_mode={self.polarization_mode}",
            f"orbit_direction={self.orbit_direction}",
            f"product_type={self.product_type}",
            f"range_date={self.initial_date} to {self.last_date}",
            f"output_dir={self.output_dir}"
        ]
        description = ", ".join(attributes)
        return f"Sentinel-1({description})"

    def get_query(
        self, 
        tile_id: str, 
        initial_date: str, 
        last_date: str,
    ) -> str:
        """
        Constructs an OData query for retrieving Sentinel-1 products 
        from the Copernicus Data Space API.

        Args:
            tile_id (str): An ID for the footprint of interset.
            initial_date (str): The start date for the query in the 
                                format 'YYYY-MM-DD'.
            last_date (str): The end date for the query in the format 
                             'YYYY-MM-DD'.

        Returns:
            str: A formatted OData query string.
        """
        aoi = self.footprints[tile_id]
        footprint = ", ".join(aoi)
        return S1_QUERY.format(
            data_url=self.data_url,
            data_collection=self.data_collection,
            initial_date=initial_date,
            last_date=last_date,
            footprint=footprint,
            orbit_direction=self.orbit_direction,
            product_type=self.product_type,
        )

    def filter_images(self, files_list: list[str]) -> list[str]:
        """
        Filters image files based on specific criteria.

        Args:
            files_list (list of str): List of file paths to be filtered.

        Returns:
            list of str: A filtered list of file paths that match the criteria.

        Notes:
            - Keeps only files whose name matches one of the requested
              `polarization_mode` values (e.g. "VV", "VH"), which Sentinel-1
              SAFE products encode directly in each file's name.
        """
        polarizations = [pol.lower() for pol in self.polarization_mode]
        return [
            file 
            for file in files_list 
            if any(pol in file.lower() for pol in polarizations)
        ]

    def download(self) -> RunSummary:
        """
        Initiates the download process for all specified Sentinel-1 AOIs.

        This method:
        1. Prints a summary of the current download configuration
           (`self.__repr__()`).
        2. Iterates over all tile IDs stored in `self.tile_ids`.
        3. Calls `self.download_tile(tile_id)` to handle the download process
           for each tile.

        Returns:
            RunSummary: The outcome of downloading every AOI, for use by
            callers that want to report on or inspect what happened.

        Notes:
            - The `self.download_tile()` method is responsible for querying
              and downloading products.
            - This function acts as the main entry point for triggering the
              download process.
        """
        logger.info(self)
        run_summary = RunSummary()
        for tile_id in self.footprints:
            run_summary.tiles.append(self.download_tile(tile_id))
        return run_summary

    def validate_download(self, file_path: Path) -> None:
        """
        Validates the downloaded file.

        Raises:
            Exception: If the file is corrupt or unreadable.
        """
        if file_path.suffix.lower() not in {".tif", ".tiff"}:
            return
        try:
            with rasterio.open(file_path) as src:
                _ = src.meta
        except Exception as e:
            message = f"Invalid TIFF file: {e}"
            logger.error(message)
            raise ValueError(message) from e

    def _create_status(
        self, 
        product: SentinelProduct,
    ) -> Sentinel1DownloadStatus:
        return Sentinel1DownloadStatus(
            product_id=product.id,
            product_name=product.name,
            orbit_direction=self.orbit_direction,
            polarization_mode=self.polarization_mode,
        )