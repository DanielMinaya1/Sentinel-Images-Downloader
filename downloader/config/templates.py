S2_QUERY = (
    "{data_url}/Products?$filter=Collection/Name eq '{data_collection}' and "
    "ContentDate/Start ge {initial_date} and "
    "ContentDate/End le {last_date} and "
    "contains(Name, '{tile_id}') and "
    "contains(Name, '{product_level}') and "
    "contains(Name, '{orbit_number}') and "
    "Online eq True&$top=500&$orderby=ContentDate/Start asc"
)

S2_QUERY_NO_ORBIT = (
    "{data_url}/Products?$filter=Collection/Name eq '{data_collection}' and "
    "ContentDate/Start ge {initial_date} and "
    "ContentDate/End le {last_date} and "
    "contains(Name, '{tile_id}') and "
    "contains(Name, '{product_level}') and "
    "Online eq True&$top=500&$orderby=ContentDate/Start asc"
)

S1_QUERY = (
    "{data_url}/Products?$filter=Collection/Name eq '{data_collection}' and "
    "ContentDate/Start ge {initial_date} and "
    "ContentDate/End le {last_date} and "
    "OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(({footprint}))') and "
    "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'orbitDirection' and "
    "att/OData.CSC.StringAttribute/Value eq '{orbit_direction}') and "
    "contains(Name, '{product_type}') and "
    "not (contains(Name, 'COG')) and "
    "Online eq True&$top=20&$orderby=ContentDate/Start asc"
)

S2_TILE_DISCOVERY_QUERY = (
    "{data_url}/Products?$filter=Collection/Name eq 'SENTINEL-2' and "
    "OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(({bbox_ring}))')"
    "&$top=20&$orderby=ContentDate/Start desc"
)
