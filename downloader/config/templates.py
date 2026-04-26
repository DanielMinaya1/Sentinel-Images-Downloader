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