from downloader.base_downloader import SentinelDownloader
from downloader.utils import load_json
from pathlib import Path 

class Sentinel1(SentinelDownloader):
    def __init__(self, username, password, footprints_path, orbit_direction,
        product_type, polarization_mode, initial_date, last_date, output_dir):   
        """
        Args:
            footprints_path (str): Path to a JSON file containing AOI footprints.
            orbit_direction (str): Orbit direction (can be "ASCENDING" or "DESCENDING").
            product_type (str): Sentinel-1 product type (e.g., "GRDH", "SLC").
            polarization_mode (list[str]): Polarization modes (e.g., ["VV", "VH"]).
        """   
        super().__init__(username, password, initial_date, last_date, output_dir)
        self.data_collection = 'SENTINEL-1'

        self.orbit_direction = orbit_direction
        self.product_type = product_type
        self.polarization_mode = polarization_mode

        self.footprints_path = Path(footprints_path)
        self.footprints = load_json(self.footprints_path)

    def __repr__(self):
        """
        Returns a string representation of the Sentinel-1 object, summarizing its key attributes.

        Includes:
        - Footprint names
        - Polarization mode
        - Orbit diretion
        - Product type
        - Date range (initial to last date)
        - Output directory

        Example:
            Sentinel-1(footprints=['T19HCC', 'T19KCP'], polarization_mode=['VV', 'VH'], 
                       orbit_direction='DESCENDING', product_type='GRD', range_date='2023-01-01 to 2023-12-31', 
                       output_dir='/data/sentinel1/')
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

    def get_query(self, tile_id, initial_date, last_date):
        """
        Constructs an OData query for retrieving Sentinel-1 products from the Copernicus Data Space API.

        Args:
            tile_id (str): An ID for the footprint of interset.
            initial_date (str): The start date for the query in the format 'YYYY-MM-DD'.
            last_date (str): The end date for the query in the format 'YYYY-MM-DD'.

        Returns:
            str: A formatted OData query string.
        """
        aoi = self.footprints[tile_id]
        footprint = ", ".join(aoi)
        query = [
            f"{self.data_url}/Products?$filter=Collection/Name eq '{self.data_collection}'",
            f"ContentDate/Start ge {initial_date}",
            f"ContentDate/End le {last_date}",
            f"OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(({footprint}))')",
            "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'orbitDirection'",
            f"att/OData.CSC.StringAttribute/Value eq '{self.orbit_direction}')",
            f"contains(Name, '{self.product_type}')",
            "not (contains(Name, 'COG'))",
            "Online eq True&$top=20&$orderby=ContentDate/Start asc",
        ]
        return " and ".join(query)

    def filter_images(self, files_list):
        """
        Filters image files based on specific criteria.

        Args:
            files_list (list of str): List of file paths to be filtered.

        Returns:
            list of str: A filtered list of file paths that match the criteria.

        Notes:
            - In this case, filter_images is the identity.
              Download all the files for processing later.
        """
        return files_list

    def download(self):
        """
        Initiates the download process for all specified Sentinel-1 AOIs.

        This method:
        1. Prints a summary of the current download configuration (`self.__repr__()`).
        2. Iterates over all tile IDs stored in `self.tile_ids`.
        3. Calls `self.download_tile(tile_id)` to handle the download process for each tile.

        Notes:
            - The `self.download_tile()` method is responsible for querying and downloading products.
            - This function acts as the main entry point for triggering the download process.
        """
        print(self)
        for tile_id in self.footprints:
            self.download_tile(tile_id)