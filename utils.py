from xml_utils import parse_xml_from_response
from datetime import datetime
from tqdm import tqdm
import requests
import os

data_collection = 'SENTINEL-2'
data_url = 'https://catalogue.dataspace.copernicus.eu/odata/v1'

def get_keycloak(username, password):
    data = {
        'client_id': 'cdse-public',
        'username': username,
        'password': password,
        'grant_type': 'password',
    }

    try:
        response = requests.post(
            'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token',
            data=data, 
            verify=True, 
            allow_redirects=True
        )
        response.raise_for_status()

    except Exception as e:
        raise Exception(
            f"Keycloak token creation failed. Reponse from the server was: {response.json()}"
        )

    return response.json()['access_token']

def process_dates(initial_date, end_date):
    formatted_start = f'{initial_date}T00:00:00.000Z'
    formatted_end = f'{end_date}T23:59:59.999Z'

    start = datetime.strptime(initial_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    yearly_ranges = []
    current_start = start

    while current_start <= end:
        year_end = datetime(current_start.year, 12, 31)
        current_end = min(year_end, end)
        yearly_ranges.append((current_start.strftime("%Y-%m-%d"), current_end.strftime("%Y-%m-%d")))
        current_start = datetime(current_start.year + 1, 1, 1)

    return yearly_ranges

def process_dates(initial_date, end_date):
    start = datetime.strptime(initial_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    yearly_ranges = []
    current_start = start

    while current_start <= end:
        year_end = datetime(current_start.year, 12, 31)
        current_end = min(year_end, end)

        yearly_ranges.append((
            f'{current_start.strftime("%Y-%m-%d")}T00:00:00.000Z',
            f'{current_end.strftime("%Y-%m-%d")}T23:59:59.999Z'
        ))

        current_start = datetime(current_start.year + 1, 1, 1)

    return yearly_ranges

def get_files(session, url):
    response = session.get(url, allow_redirects=True)
    if response.status_code == 200:
        xmldict, namespace = parse_xml_from_response(response)
        general_info_key = f'{namespace}General_Info'
        files_list = xmldict[
            general_info_key
        ]['Product_Info']['Product_Organisation']['Granule_List']['Granule']['IMAGE_FILE']
        return files_list
    return []

def download_data(tile_id, initial_date, end_date, level, output_directory, access_token, bands):
    base_url = f"{data_url}/Products?$filter="
    collection_filter = f"Collection/Name eq '{data_collection}' and "
    name_filter = f"contains(Name, '{tile_id}') and contains(Name, '{level}') and "
    status_filter =  "Online eq True and "
    date_filter = f"ContentDate/Start gt {initial_date} and ContentDate/End lt {end_date}"
    extra_options = f"&$top=500&$orderby=ContentDate/Start asc"
    
    query_url = f"{base_url}{collection_filter}{name_filter}{status_filter}{date_filter}{extra_options}"
    response = requests.get(query_url)
    response.raise_for_status()
    data = response.json()

    session = requests.Session()
    session.headers.update({'Authorization': f'Bearer {access_token}'})
    
    for entry in tqdm(data['value'], desc=f"Downloading {tile_id} from {initial_date[:10]} to {end_date[:10]}"):
        print()
        product_id = entry['Id']
        product_name = entry['Name']

        url = f"{data_url}/Products({product_id})/Nodes({product_name})/Nodes(MTD_MSIL2A.xml)/$value"
        response = session.get(url , allow_redirects=False)
        url_location = response.headers['Location']

        files_list = get_files(session, url_location)
        files_list = [f'{file}.jp2' for file in files_list if any(band in file for band in bands)]
        for file in files_list:
            outfile_path = os.path.join(output_directory, tile_id, product_name, file)
            os.makedirs(os.path.dirname(outfile_path), exist_ok=True)
            if not os.path.isfile(outfile_path):
                nodes_str = "/".join([f"Nodes({node})" for node in file.split("/")])
                url_full = f"{data_url}/Products({product_id})/Nodes({product_name})/{nodes_str}/$value"
                response = session.get(url_full, allow_redirects=False)
                url_full_location = response.headers['Location']
                file_response = session.get(url_full_location, allow_redirects=True)

                print(f"Downloading {outfile_path}")
                with open(outfile_path, 'wb') as f:
                    f.write(file_response.content)
            if os.path.getsize(outfile_path) < 100:
                print(f"Corrupted file {outfile_path}")
                os.remove(outfile_path)