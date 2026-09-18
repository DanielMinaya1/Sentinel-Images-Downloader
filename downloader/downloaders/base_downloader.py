import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path

import requests
from tqdm import tqdm

from downloader.config.endpoints import DATA_URL, DOWNLOAD_URL
from downloader.models import (
    DownloadStatus,
    FileDownloadResult,
    RunSummary,
    SentinelDownloadStatus,
    SentinelProduct,
    SentinelResponse,
    TileDownloadSummary,
)
from downloader.utils.auth import get_keycloak
from downloader.utils.dates import process_dates
from downloader.utils.io import download_file, process_path
from downloader.utils.xml import get_files, parse_manifest

logger = logging.getLogger(__name__)

TOKEN_LIFETIME = 3600  # Copernicus tokens last 1 hour
TOKEN_REFRESH_MARGIN = 300  # Refresh 5 minutes early


class SentinelDownloader(ABC):
    response_class: type[SentinelResponse] = SentinelResponse

    def __init__(
        self,
        username: str,
        password: str,
        initial_date: str,
        last_date: str,
        output_dir: str,
        max_retries: int,
    ):
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

        self.output_dir = Path(output_dir).resolve()

        self.max_retries = max_retries

        self._session: requests.Session | None = None
        self._token_created_at: float | None = None  # Unix timestamp

    def _is_token_expired(self) -> bool:
        if self._token_created_at is None:
            return True
        elapsed = time.time() - self._token_created_at
        return elapsed >= (TOKEN_LIFETIME - TOKEN_REFRESH_MARGIN)

    def _refresh_session(self) -> None:
        """Creates or refreshes the session with a new Keycloak token."""
        logger.info("Refreshing Keycloak token...")
        if self._session is not None:
            self._session.close()

        access_token = get_keycloak(
            username=self.username,
            password=self.password,
        )
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
            }
        )
        self._token_created_at = time.time()
        logger.info("Session refreshed successfully.")

    @property
    def session(self) -> requests.Session:
        """Returns a valid session, refreshing the token if needed."""
        if self._session is None or self._is_token_expired():
            self._refresh_session()
        return self._session

    def prepare_output(self, product_name):
        """
        Creates and returns the output directory for a given product.

        This method ensures that the directory exists before returning
        its path.

        Args:
            product_name (str): Name of the product for which the output
            directory is created.

        Returns:
            pathlib.Path: Path to the created (or existing) output directory.
        """
        product_path = self.output_dir / product_name
        product_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created output directory for the files: {product_path}")
        return product_path

    @abstractmethod
    def get_query(
        self,
        tile_id: str,
        initial_date: str,
        last_date: str,
    ) -> str:
        """Abstract method to be implemented by subclasses."""
        pass

    @abstractmethod
    def filter_images(
        self,
        files_list: list[str],
    ) -> list[str]:
        """Abstract method to be implemented by subclasses."""
        pass

    @abstractmethod
    def _create_status(
        self,
        product: SentinelProduct,
    ) -> SentinelDownloadStatus:
        """Builds the satellite-specific status object
        for a given product."""
        pass

    def _download_with_retries(
        self,
        url: str,
        file_path: Path,
    ) -> FileDownloadResult:
        """
        Downloads a single file, retrying on failure.

        Unlike the previous implementation, a failed HTTP response
        (4xx/5xx) is never written to disk: `raise_for_status()`
        is checked before the body is saved, so a bad response
        cannot masquerade as a valid downloaded file.
        """
        last_error: str | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, allow_redirects=True)
                response.raise_for_status()
                download_file(response, file_path)
                self.validate_download(file_path)
                return FileDownloadResult(
                    file_path=file_path,
                    status=DownloadStatus.SUCCESS,
                    attempts=attempt,
                )

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Attempt {attempt} failed for {file_path}: {e}",
                )
                file_path.unlink(missing_ok=True)

                if attempt < self.max_retries:
                    logger.info(f"Retrying download for {file_path}...")

        logger.error(f"Max retries reached for {file_path}. Giving up.")
        return FileDownloadResult(
            file_path=file_path,
            status=DownloadStatus.FAILED,
            attempts=self.max_retries,
            error=last_error,
        )

    def download_product(
        self,
        product: SentinelProduct,
    ) -> SentinelDownloadStatus:
        """
        Downloads a Sentinel product and its relevant files.

        This method:
        1. Creates an output directory for the product.
        2. Downloads the `manifest.safe` file if it does not already exist.
        3. Parses the manifest file to retrieve the list of image files.
        4. Filters image files based on predefined criteria.
        5. Downloads the filtered image files if they do not already exist.

        Args:
            product (SentinelProduct): Metadata for the product to download.

        Returns:
            SentinelDownloadStatus: The outcome of the download, including a
            per-file breakdown of successes, skips, and failures.

        Notes:
            - The function ensures that files are downloaded only if they
              are missing.
            - The folder structure is preserved to match the Sentinel-2
              SAFE format.
        """
        product_base_url = "/".join(
            [
                self.download_url,
                f"Products({product.id})",
                f"Nodes({product.name})",
            ]
        )
        product_path = self.prepare_output(product.name)
        status = self._create_status(product)

        manifest_path = product_path / "manifest.safe"
        if not manifest_path.is_file():
            manifest_url = f"{product_base_url}/Nodes(manifest.safe)/$value"
            manifest_result = self._download_with_retries(
                manifest_url,
                manifest_path,
            )
            status.files.append(manifest_result)
            if manifest_result.status == DownloadStatus.FAILED:
                status.error = manifest_result.error
                return status

        try:
            xmldict = parse_manifest(manifest_path)
            files_list = self.filter_images(get_files(xmldict))
        except Exception as e:
            status.error = f"Failed to parse manifest: {e}"
            logger.error(status.error, exc_info=True)
            return status

        logger.info(f"Found {len(files_list)} files to download")

        for file in files_list:
            file_path = product_path / file
            file_path = process_path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if file_path.is_file():
                logger.info(f"{file_path} already exists. Skipping...")
                status.files.append(
                    FileDownloadResult(
                        file_path=file_path,
                        status=DownloadStatus.SKIPPED,
                    ),
                )
                continue

            nodes_str = "/".join([f"Nodes({node})" for node in file.split("/")])
            file_url = f"{product_base_url}/{nodes_str}/$value"
            status.files.append(
                self._download_with_retries(file_url, file_path),
            )

        return status

    def download_tile(self, tile_id: str) -> TileDownloadSummary:
        """
        Downloads all Sentinel products for a given tile across
        multiple date ranges.

        This method:
        1. Iterates through predefined date ranges.
        2. Constructs a query to fetch available Sentinel products for
           the tile.
        3. Sends a request to retrieve product metadata.
        4. Iterates through each product, initializing a session and
           downloading the product files.
        5. Introduces a delay between requests to prevent excessive
           API calls.

        Args:
            tile_id (str): The Sentinel tile ID to download data for.

        Returns:
            TileDownloadSummary: The outcome of downloading every product
            found for this tile, across all date ranges.

        Notes:
            - Uses `self.get_query()` to construct the API request URL.
            - Uses `self.download_product()` to handle the actual file
              downloads.
            - Introduces a **10-second delay** (`time.sleep(10)`) between
              iterations to avoid rate limits.
        """
        summary = TileDownloadSummary(tile_id=tile_id)
        for initial_date, last_date in self.date_ranges:
            logger.info(f"Downloading from {initial_date} to {last_date}")
            query = self.get_query(tile_id, initial_date, last_date)
            raw_response = requests.get(query)
            raw_response.raise_for_status()
            response = self.response_class.from_json(raw_response.json())

            desc = f"Downloading tile {tile_id} from {initial_date[:10]} to {last_date[:10]}"
            progress = tqdm(response.products, desc=desc)
            for product in progress:
                summary.products.append(self.download_product(product))
                progress.set_postfix(
                    succeeded=summary.succeeded,
                    failed=summary.failed,
                    skipped=summary.skipped,
                )

            time.sleep(10)
        return summary

    @abstractmethod
    def download(self) -> RunSummary:
        """Abstract method to be implemented by subclasses."""
        pass

    @abstractmethod
    def validate_download(self, file_path: Path) -> None:
        """Abstract method to be implemented by subclasses."""
        pass
